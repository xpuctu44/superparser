from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from .deps import get_session
from . import crud
from .models import Product
from .auth import get_current_user
from .config import settings
from sqlalchemy import select
from .models import Store
from .scraper import discover_products
import asyncio
from datetime import datetime
from collections import defaultdict


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html", "xml"]))


router = APIRouter()
@router.get("/compare/add", response_class=HTMLResponse)
def compare_add_form(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    stores = crud.list_stores(db, user_id=user.id)
    # Get existing groups for dropdown
    items = crud.list_products(db, user_id=user.id)
    existing_groups = sorted({p.group_key for p in items})
    tmpl = env.get_template("compare_add.html")
    return tmpl.render(stores=stores, existing_groups=existing_groups)


@router.post("/compare/add")
async def compare_add_submit(
    group_key: str = Form(...),
    request: Request = None,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)  # type: ignore[arg-type]
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    stores = crud.list_stores(db, user_id=user.id)
    group = group_key.strip()
    if not group:
        raise HTTPException(status_code=400, detail="Group is required")
    created = 0
    form = await request.form()  # type: ignore[assignment]
    for s in stores:
        field = f"url_{s.id}"
        url_val = form.get(field)  # type: ignore[arg-type]
        url = (url_val or "").strip()
        if not url:
            continue
        existing = db.scalar(select(Product).where(Product.user_id == user.id, Product.store_id == s.id, Product.group_key == group))
        if existing:
            if existing.product_url != url:
                existing.product_url = url
                db.commit()
            continue
        prod = Product(user_id=user.id, store_id=s.id, title=group, product_url=url, group_key=group)
        db.add(prod)
        db.commit()
        created += 1
    return RedirectResponse(url=f"/products?imported={created}", status_code=303)


@router.get("/stores", response_class=HTMLResponse)
def stores(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    items = crud.list_stores(db, user_id=user.id)
    primary = crud.get_primary_store(db, user_id=user.id)
    tmpl = env.get_template("stores.html")
    html = tmpl.render(app_name=settings.app_name, items=items, primary=primary)
    return HTMLResponse(content=html)


@router.get("/stores/view", response_class=HTMLResponse)
def stores_view(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    items = crud.list_stores(db, user_id=user.id)
    primary = crud.get_primary_store(db, user_id=user.id)
    tmpl = env.get_template("stores.html")
    html = tmpl.render(app_name=settings.app_name, items=items, primary=primary)
    return HTMLResponse(content=html)


@router.post("/stores")
def create_store(
    slug: str = Form(...),
    name: str = Form(...),
    base_url: str = Form(""),
    price_selector: str = Form(None),
    request: Request = None,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)  # type: ignore[arg-type]
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    if crud.get_store_by_slug(db, user.id, slug):
        raise HTTPException(status_code=400, detail="Store with slug exists")
    crud.create_store(db, user_id=user.id, slug=slug, name=name, base_url=base_url, price_selector=price_selector)
    return RedirectResponse(url="/stores/view", status_code=303)


@router.get("/stores/{store_id}/auto-import", response_class=HTMLResponse)
def auto_import_form(store_id: int, request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    s = db.get(Store, store_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404)
    tmpl = env.get_template("stores_auto_import.html")
    return tmpl.render(store=s)


@router.post("/stores/{store_id}/auto-import")
async def auto_import_trigger(
    store_id: int,
    request: Request,
    list_pages: str = Form(""),
    product_link_selector: str = Form(""),
    title_selector: str = Form(""),
    price_selector_override: str = Form(""),
    clear_before: str = Form(""),
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    s = db.get(Store, store_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404)
    cfg = crud.upsert_store_scrape_config(
        db,
        user_id=user.id,
        store_id=store_id,
        list_pages=list_pages,
        product_link_selector=product_link_selector,
        title_selector=title_selector or None,
        price_selector_override=price_selector_override or None,
        model_regex=None,
        capacity_regex=None,
        color_regex=None,
    )
    pages = [p.strip() for p in (cfg.list_pages or "").splitlines() if p.strip()]
    if not pages:
        return HTMLResponse("<h3>Ошибка: укажите хотя бы один URL категории</h3>", status_code=400)
    try:
        # optional clear
        if (clear_before or "").lower() in ("1", "true", "on", "yes"):
            crud.delete_products_by_store(db, user_id=user.id, store_id=store_id)
        items: list[dict] = await discover_products(pages, link_selector=(cfg.product_link_selector or None), title_selector=cfg.title_selector)
        created = crud.import_discovered_products(db, user_id=user.id, store_id=store_id, items=items)
        return RedirectResponse(url=f"/products?imported={created}", status_code=303)
    except Exception as e:
        return HTMLResponse(f"<h3>Ошибка авто-импорта</h3><pre>{str(e)}</pre>", status_code=500)


@router.post("/stores/{store_id}/make-primary")
def make_primary_store(store_id: int, request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    # ensure store belongs to user
    s = db.get(Store, store_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404)
    crud.set_primary_store(db, user_id=user.id, store_id=store_id)
    return RedirectResponse(url="/stores/view", status_code=303)


@router.post("/stores/create-primary")
def create_primary_store(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    # if primary exists for this user by slug, just redirect
    slug = settings.primary_store_slug or "my-store"
    existing = crud.get_store_by_slug(db, user.id, slug)
    if not existing:
        crud.create_store(
            db,
            user_id=user.id,
            slug=slug,
            name="Мой магазин",
            base_url=settings.primary_store_base_url or "",
            price_selector=None,
        )
    return RedirectResponse(url="/stores/view", status_code=303)


@router.post("/stores/unset-primary")
def unset_primary(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    crud.unset_primary_store(db, user_id=user.id)
    return RedirectResponse(url="/stores/view", status_code=303)


@router.post("/stores/{store_id}/delete")
def delete_store(store_id: int, request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    s = db.get(Store, store_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404)
    crud.delete_store(db, user_id=user.id, store_id=store_id)
    return RedirectResponse(url="/stores/view", status_code=303)


@router.post("/stores/{store_id}/delete-products")
def delete_store_products(store_id: int, request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    s = db.get(Store, store_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404)
    crud.delete_products_by_store(db, user_id=user.id, store_id=store_id)
    return RedirectResponse(url="/stores/view", status_code=303)


@router.get("/products", response_class=HTMLResponse)
def products(request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    stores = crud.list_stores(db, user_id=user.id)
    items = crud.list_products(db, user_id=user.id)
    # distinct group keys for dropdown
    existing_groups = sorted({p.group_key for p in items})
    
    # Group products by group_key
    grouped = defaultdict(list)
    for p in items:
        grouped[p.group_key].append(p)
    
    # Create groups dict with first product as representative and all products for modal
    groups = {}
    for group_key, products_list in grouped.items():
        groups[group_key] = {
            "representative": products_list[0],  # First product for display
            "products": products_list  # All products for modal
        }
    
    imported = None
    updated = None
    try:
        q = dict(request.query_params)
        if "imported" in q:
            imported = int(q["imported"])  # type: ignore[arg-type]
        if "updated" in q:
            updated = int(q["updated"])  # type: ignore[arg-type]
    except Exception:
        imported = None
        updated = None
    tmpl = env.get_template("products.html")
    html = tmpl.render(app_name=settings.app_name, groups=groups, stores=stores, existing_groups=existing_groups, imported=imported, updated=updated)
    return HTMLResponse(content=html)


@router.post("/products")
def create_product(
    store_id: int = Form(...),
    group_key_select: str = Form(""),
    group_key_new: str = Form(""),
    # legacy fields support
    title: str = Form(None),  # type: ignore[assignment]
    group_key: str = Form(None),  # type: ignore[assignment]
    product_url: str = Form(...),
    request: Request = None,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)  # type: ignore[arg-type]
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    # prefer new fields; fallback to legacy names if present
    chosen_group = (group_key_new or "").strip() or (group_key_select or "").strip() or (group_key or "").strip()
    if not chosen_group:
        raise HTTPException(status_code=400, detail="Group key is required")
    title = chosen_group if not title else title
    prod = crud.add_product(db, user_id=user.id, store_id=store_id, title=title, product_url=product_url, group_key=chosen_group)
    return RedirectResponse(url="/products", status_code=303)


@router.post("/products/add-to-group")
def add_product_to_group(
    group_key: str = Form(...),
    store_id: int = Form(...),
    product_url: str = Form(...),
    title: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)  # type: ignore[arg-type]
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    # Check if product already exists for this group+store
    existing = db.scalar(select(Product).where(Product.user_id == user.id, Product.store_id == store_id, Product.group_key == group_key))
    if existing:
        # Update URL if different
        if existing.product_url != product_url:
            existing.product_url = product_url
            db.commit()
        return RedirectResponse(url="/products", status_code=303)
    # Create new product
    title = title.strip() or group_key
    prod = crud.add_product(db, user_id=user.id, store_id=store_id, title=title, product_url=product_url, group_key=group_key)
    return RedirectResponse(url="/products", status_code=303)


@router.post("/products/bulk")
def bulk_import_products(
    store_id: int = Form(...),
    lines: str = Form(""),
    request: Request = None,
    db: Session = Depends(get_session),
):
    user = get_current_user(request, db)  # type: ignore[arg-type]
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    created = 0
    updated = 0
    for raw in (lines or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        group_key = title = url = None
        if len(parts) == 3:
            group_key, title, url = parts
        elif len(parts) == 2:
            group_key, url = parts
            title = group_key
        elif len(parts) == 1:
            url = parts[0]
            # derive group from URL path
            from urllib.parse import urlparse
            last = [p for p in urlparse(url).path.split("/") if p][-1] if url else ""
            group_key = title = last or url
        else:
            continue
        if not (group_key and url):
            continue
        # upsert by (group_key, store_id)
        existing = db.scalar(select(Product).where(Product.user_id == user.id, Product.store_id == store_id, Product.group_key == group_key))
        if existing:
            if existing.product_url != url or (title and existing.title != title):
                existing.product_url = url
                if title:
                    existing.title = title
                db.commit()
                updated += 1
            continue
        prod = Product(user_id=user.id, store_id=store_id, title=title or group_key, product_url=url, group_key=group_key)
        db.add(prod)
        db.commit()
        created += 1
    return RedirectResponse(url=f"/products?imported={created}&updated={updated}", status_code=303)


@router.post("/products/{product_id}/delete")
def delete_product(product_id: int, request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    # minimal check: ensure product belongs to user
    prod = db.get(Product, product_id)
    if not prod or prod.user_id != user.id:
        raise HTTPException(status_code=404)
    crud.delete_product(db, product_id)
    return RedirectResponse(url="/products", status_code=303)


@router.get("/products/{product_id}/history", response_class=HTMLResponse)
def product_history(product_id: int, request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    prod = db.get(Product, product_id)
    if not prod or prod.user_id != user.id:
        raise HTTPException(status_code=404)
    from sqlalchemy import select as _select
    from .models import PriceSnapshot
    snaps = list(db.scalars(_select(PriceSnapshot).where(PriceSnapshot.product_id == product_id).order_by(PriceSnapshot.captured_at)))
    # prepare points
    points = []
    for s in snaps:
        ts = int(s.captured_at.timestamp()) if isinstance(s.captured_at, datetime) else 0
        points.append({"t": ts, "y": s.price})
    tmpl = env.get_template("product_history.html")
    return tmpl.render(product=prod, points=points)


@router.get("/compare/history", response_class=HTMLResponse)
def compare_group_history(group: str, request: Request, db: Session = Depends(get_session)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/auth/login", status_code=303)
    group_key = group
    # load products for this group across stores
    prods = list(db.scalars(select(Product).where(Product.user_id == user.id, Product.group_key == group_key)))
    from .models import PriceSnapshot, Store as _Store
    store_by_id = {s.id: s for s in db.scalars(select(_Store).where(_Store.user_id == user.id))}
    series = []
    for p in prods:
        snaps = list(db.scalars(select(PriceSnapshot).where(PriceSnapshot.product_id == p.id).order_by(PriceSnapshot.captured_at)))
        points = []
        for s in snaps:
            ts = int(s.captured_at.timestamp()) if isinstance(s.captured_at, datetime) else 0
            points.append({"t": ts, "y": s.price})
        store = store_by_id.get(p.store_id)
        series.append({
            "store": store.name if store else f"Store {p.store_id}",
            "color": None,
            "points": points,
        })
    tmpl = env.get_template("compare_history.html")
    return tmpl.render(group=group_key, series=series)

