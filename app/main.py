from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from .config import settings
from .database import init_db
from .routers import router as ui_router
from sqlalchemy.orm import Session
from sqlalchemy import select
from .deps import get_session
from .compare import build_comparison_matrix
from .models import Store
from . import crud
from .scheduler import start_scheduler, refresh_prices_once, reload_user_jobs
from .auth_routes import router as auth_router
from .auth import get_current_user
from .settings_routes import router as settings_router
from .telegram_webhook import router as telegram_router


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
)

app = FastAPI(title=settings.app_name)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    template = env.get_template("index.html")
    html = template.render(
        app_name=settings.app_name,
        is_authenticated=bool(user),
    )
    return HTMLResponse(content=html)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
# start scheduler
    import asyncio
    loop = asyncio.get_event_loop()
    start_scheduler(loop)
    reload_user_jobs()


# UI routes
app.include_router(ui_router)
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(telegram_router)


@app.get("/compare", response_class=HTMLResponse)
async def compare_view(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    # Show primary store first, then others by slug
    stores = list(db.scalars(select(Store).where(Store.user_id == user.id).order_by(Store.slug)))
    primary = crud.get_primary_store(db, user_id=user.id)
    if primary:
        stores = sorted(stores, key=lambda s: (0 if s.id == primary.id else 1, s.slug))
    matrix = build_comparison_matrix(db, user_id=user.id)
    template = env.get_template("compare.html")
    
    # Get query parameters for messages
    updated = None
    error = None
    try:
        q = dict(request.query_params)
        if "updated" in q:
            updated = int(q["updated"])
        if "error" in q:
            error = True
    except Exception:
        pass
    
    html = template.render(app_name=settings.app_name, stores=stores, matrix=matrix, updated=updated, error=error)
    return HTMLResponse(content=html)


@app.post("/compare/refresh")
async def compare_refresh(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    try:
        # refresh_prices_once returns (updated_count, changes_by_user)
        updated_count, _ = await refresh_prices_once()
        # Redirect with success message
        return RedirectResponse(url=f"/compare?updated={updated_count}", status_code=303)
    except Exception as e:
        # Log error and redirect with error message
        import logging
        logging.error(f"Error refreshing prices: {e}")
        return RedirectResponse(url="/compare?error=1", status_code=303)

