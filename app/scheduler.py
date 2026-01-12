from __future__ import annotations

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from sqlalchemy import select
from .database import SessionLocal
from .models import Product, Store, User, PriceSnapshot
from .scraper import fetch_price
from .crud import add_price_snapshot
from .config import settings
from .notifier import send_telegram_message


scheduler = None  # type: AsyncIOScheduler | None
USER_JOB_PREFIX = "user_refresh_"


async def refresh_prices_once() -> tuple[int, dict[int, list[str]]]:
    updated = 0
    changes_by_user: dict[int, list[str]] = {}
    db: Session = SessionLocal()
    try:
        stores = {s.id: s for s in db.scalars(select(Store))}
        for p in db.scalars(select(Product)):
            store = stores.get(p.store_id)
            if not store:
                continue
            price = await fetch_price(p.product_url, css_selector=store.price_selector)
            if price is not None:
                # get previous latest price BEFORE adding new
                prev = db.scalar(select(PriceSnapshot).where(PriceSnapshot.product_id == p.id).order_by(PriceSnapshot.captured_at.desc()))
                add_price_snapshot(db, product_id=p.id, price=price)
                updated += 1
                if prev and abs(prev.price - price) > 1e-6:
                    diff = price - prev.price
                    arrow = "⬆️" if diff > 0 else "⬇️"
                    line = f"{arrow} {p.group_key} · {store.name}: {prev.price:.0f} → {price:.0f} {prev.currency}"
                    changes_by_user.setdefault(p.user_id, []).append(line)
    finally:
        db.close()
    return updated, changes_by_user


async def scheduled_job():
    # For now: global refresh + notify all users who have chat ids
    count, changes_by_user = await refresh_prices_once()
    db: Session = SessionLocal()
    try:
        for user in db.scalars(select(User)):
            if user.telegram_chat_id:
                changes = changes_by_user.get(user.id) or []
                if changes:
                    body = "\n".join(changes[:50])  # limit to avoid very long messages
                    text = f"<b>Проверка цен завершена</b>\nИзменений: {len(changes)} из {count}\n\n{body}"
                else:
                    text = f"<b>Проверка цен завершена</b>\nОбновлено позиций: {count}\nИзменений не обнаружено"
                await send_telegram_message(text)
    finally:
        db.close()


def start_scheduler(loop):
    global scheduler
    scheduler = AsyncIOScheduler(event_loop=loop, timezone=settings.timezone)
    scheduler.add_job(scheduled_job, CronTrigger.from_crontab(settings.schedule_cron_1))
    scheduler.add_job(scheduled_job, CronTrigger.from_crontab(settings.schedule_cron_2))
    scheduler.start()


def reload_user_jobs():
    if not scheduler:
        return
    # Remove previous user jobs
    for job in list(scheduler.get_jobs()):
        if job.id and job.id.startswith(USER_JOB_PREFIX):
            scheduler.remove_job(job.id)
    db: Session = SessionLocal()
    try:
        for user in db.scalars(select(User)):
            for idx, cron in enumerate([user.cron_1, user.cron_2], start=1):
                if cron:
                    scheduler.add_job(
                        scheduled_job,
                        CronTrigger.from_crontab(cron),
                        id=f"{USER_JOB_PREFIX}{user.id}_{idx}",
                        replace_existing=True,
                    )
    finally:
        db.close()

