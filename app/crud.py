from typing import Iterable, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from .models import Store, Product, PriceSnapshot, User, UserPreference, StoreScrapeConfig


# Stores
def create_store(db: Session, *, user_id: int, slug: str, name: str, base_url: Optional[str] = None, price_selector: Optional[str] = None) -> Store:
    store = Store(user_id=user_id, slug=slug, name=name, base_url=base_url or "", price_selector=price_selector)
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def get_store_by_slug(db: Session, user_id: int, slug: str) -> Optional[Store]:
    stmt = select(Store).where(Store.user_id == user_id, Store.slug == slug)
    return db.scalar(stmt)


def list_stores(db: Session, *, user_id: int) -> list[Store]:
    stmt = select(Store).where(Store.user_id == user_id).order_by(Store.name)
    return list(db.scalars(stmt))


def get_or_create_user_pref(db: Session, *, user_id: int) -> UserPreference:
    pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if not pref:
        pref = UserPreference(user_id=user_id)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


def set_primary_store(db: Session, *, user_id: int, store_id: int) -> UserPreference:
    pref = get_or_create_user_pref(db, user_id=user_id)
    pref.primary_store_id = store_id
    db.commit()
    db.refresh(pref)
    return pref


def get_primary_store(db: Session, *, user_id: int) -> Optional[Store]:
    pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if not pref or not pref.primary_store_id:
        return None
    return db.get(Store, pref.primary_store_id)


def unset_primary_store(db: Session, *, user_id: int) -> None:
    pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if pref and pref.primary_store_id is not None:
        pref.primary_store_id = None
        db.commit()


def delete_store(db: Session, *, user_id: int, store_id: int) -> None:
    store = db.get(Store, store_id)
    if not store or store.user_id != user_id:
        return
    # clear primary if needed
    pref = db.scalar(select(UserPreference).where(UserPreference.user_id == user_id))
    if pref and pref.primary_store_id == store_id:
        pref.primary_store_id = None
    # delete will cascade products due to FK
    db.delete(store)
    db.commit()


# Scrape config and import
def upsert_store_scrape_config(
    db: Session,
    *,
    user_id: int,
    store_id: int,
    list_pages: str,
    product_link_selector: str,
    title_selector: Optional[str],
    price_selector_override: Optional[str],
    model_regex: Optional[str] = None,
    capacity_regex: Optional[str] = None,
    color_regex: Optional[str] = None,
) -> StoreScrapeConfig:
    cfg = db.scalar(select(StoreScrapeConfig).where(StoreScrapeConfig.store_id == store_id, StoreScrapeConfig.user_id == user_id))
    if not cfg:
        cfg = StoreScrapeConfig(user_id=user_id, store_id=store_id)
        db.add(cfg)
    cfg.list_pages = list_pages
    cfg.product_link_selector = product_link_selector
    cfg.title_selector = title_selector
    cfg.price_selector_override = price_selector_override
    cfg.model_regex = model_regex
    cfg.capacity_regex = capacity_regex
    cfg.color_regex = color_regex
    db.commit()
    db.refresh(cfg)
    return cfg


def import_discovered_products(db: Session, *, user_id: int, store_id: int, items: list[dict]) -> int:
    created = 0
    for it in items:
        url = it.get("url")
        model = (it.get("model") or "").strip()
        capacity = (it.get("capacity") or "").strip()
        color = (it.get("color") or "").strip()
        group_key = " ".join([p for p in [model, capacity, color] if p])
        title = it.get("title") or group_key or model or url
        
        # Check if product already exists by (group_key, store_id)
        existing = db.scalar(select(Product).where(Product.user_id == user_id, Product.store_id == store_id, Product.group_key == group_key))
        if existing:
            # Update existing product URL if different
            if existing.product_url != url:
                existing.product_url = url
                db.commit()
            continue
            
        # Create new product
        try:
            product = Product(user_id=user_id, store_id=store_id, title=title, product_url=url, group_key=group_key)
            db.add(product)
            db.commit()
            created += 1
        except Exception:
            # If still fails due to race condition, skip
            db.rollback()
            continue
    return created


# Products
def add_product(db: Session, *, user_id: int, store_id: int, title: str, product_url: str, group_key: str) -> Product:
    product = Product(user_id=user_id, store_id=store_id, title=title, product_url=product_url, group_key=group_key)
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def delete_products_by_store(db: Session, *, user_id: int, store_id: int) -> int:
    # delete all products for this user+store
    count = 0
    for p in db.scalars(select(Product).where(Product.user_id == user_id, Product.store_id == store_id)):
        db.delete(p)
        count += 1
    if count:
        db.commit()
    return count


def list_products(db: Session, *, user_id: int, store_id: Optional[int] = None) -> list[Product]:
    stmt = select(Product).where(Product.user_id == user_id)
    if store_id is not None:
        stmt = stmt.where(Product.store_id == store_id)
    stmt = stmt.order_by(Product.title)
    return list(db.scalars(stmt))


def delete_product(db: Session, product_id: int) -> None:
    product = db.get(Product, product_id)
    if product:
        db.delete(product)
        db.commit()


# Price snapshots
def add_price_snapshot(db: Session, *, product_id: int, price: float, currency: str = "RUB") -> PriceSnapshot:
    snap = PriceSnapshot(product_id=product_id, price=price, currency=currency)
    db.add(snap)
    db.commit()
    db.refresh(snap)
    # keep only last 30 by captured_at
    snaps = list(db.scalars(select(PriceSnapshot).where(PriceSnapshot.product_id == product_id).order_by(PriceSnapshot.captured_at.desc())))
    for s in snaps[30:]:
        db.delete(s)
    if len(snaps) > 30:
        db.commit()
    return snap


def latest_prices_for_products(db: Session, product_ids: Iterable[int]) -> dict[int, PriceSnapshot]:
    # For simplicity, fetch all and reduce in Python; for production, use window functions
    stmt = select(PriceSnapshot).where(PriceSnapshot.product_id.in_(list(product_ids))).order_by(PriceSnapshot.product_id, PriceSnapshot.captured_at.desc())
    result: dict[int, PriceSnapshot] = {}
    for snap in db.scalars(stmt):
        if snap.product_id not in result:
            result[snap.product_id] = snap
    return result

