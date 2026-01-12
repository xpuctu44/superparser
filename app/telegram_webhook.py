from fastapi import APIRouter, Request, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from .database import SessionLocal
from .models import User
from .config import settings
import httpx


router = APIRouter()


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret or secret != settings.telegram_webhook_secret:
        raise HTTPException(status_code=401)
    data = await request.json()
    message = data.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id")) if chat.get("id") is not None else None
    if not text or not chat_id:
        return {"ok": True}
    if text.startswith("/start "):
        code = text.split(" ", 1)[1].strip()
        db: Session = SessionLocal()
        try:
            user = db.scalar(select(User).where(User.telegram_link_code == code))
            if user:
                user.telegram_chat_id = chat_id
                user.telegram_linked_at = __import__("datetime").datetime.utcnow()
                db.commit()
                await reply(chat_id, "✅ Telegram успешно привязан. Будете получать уведомления.")
        finally:
            db.close()
    return {"ok": True}


async def reply(chat_id: str, text: str) -> None:
    if not settings.telegram_bot_token:
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})









