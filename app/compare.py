from __future__ import annotations

from collections import defaultdict
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from .models import Store, Product, PriceSnapshot, User


def build_comparison_matrix(db: Session, *, user_id: int) -> dict[str, dict[str, Any]]:
    # rows: group_key; columns: store.slug -> price
    # fetch stores
    stores = list(db.scalars(select(Store).where(Store.user_id == user_id).order_by(Store.slug)))
    # fetch products with store eager-loaded
    products = list(db.scalars(select(Product).where(Product.user_id == user_id)))

    # latest price per product
    snaps = db.scalars(select(PriceSnapshot).order_by(PriceSnapshot.product_id, PriceSnapshot.captured_at.desc()))
    latest: dict[int, PriceSnapshot] = {}
    for s in snaps:
        if s.product_id not in latest:
            latest[s.product_id] = s

    matrix: dict[str, dict[str, Any]] = defaultdict(dict)
    for p in products:
        price = latest.get(p.id)
        if price:
            # column name by store slug
            store_slug = p.store.slug  # type: ignore[union-attr]
            row = matrix[p.group_key]
            row[store_slug] = {
                "price": price.price,
                "currency": price.currency,
                "title": p.title,
                "url": p.product_url,
            }
    return matrix

