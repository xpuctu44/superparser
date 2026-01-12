from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from .deps import get_session
from .auth import get_current_user
from .config import settings
import secrets


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html", "xml"]))


router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    tmpl = env.get_template("settings.html")
    link_url = None
    if settings.telegram_bot_username and settings.public_base_url:
        if not user.telegram_link_code:
            user.telegram_link_code = secrets.token_urlsafe(12)
            db.commit()
        link_url = f"https://t.me/{settings.telegram_bot_username}?start={user.telegram_link_code}"
    return tmpl.render(user=user, link_url=link_url)


@router.post("/settings")
def settings_update(
    request: Request,
    telegram_chat_id: str = Form(""),
    cron_1: str = Form(""),
    cron_2: str = Form(""),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    user.telegram_chat_id = telegram_chat_id or None
    user.cron_1 = cron_1 or None
    user.cron_2 = cron_2 or None
    db.commit()
    # scheduler reload handled elsewhere
    return RedirectResponse("/settings", status_code=303)

