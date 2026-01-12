from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telegram_link_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    telegram_linked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cron_1: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cron_2: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    company_id: Mapped[Optional[int]] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"), nullable=True)

    stores: Mapped[list[Store]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore
    products: Mapped[list[Product]] = relationship(back_populates="user", cascade="all, delete-orphan")  # type: ignore
class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)



class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    price_selector: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    user: Mapped[User] = relationship(back_populates="stores")  # type: ignore
    products: Mapped[list[Product]] = relationship(back_populates="store", cascade="all, delete-orphan")  # type: ignore


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("store_id", "product_url", name="uq_store_product_url"),
        UniqueConstraint("group_key", "store_id", name="uq_group_store"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    group_key: Mapped[str] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(300))
    product_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    store: Mapped[Store] = relationship(back_populates="products")  # type: ignore
    user: Mapped[User] = relationship(back_populates="products")  # type: ignore
    prices: Mapped[list[PriceSnapshot]] = relationship(back_populates="product", cascade="all, delete-orphan")  # type: ignore


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        UniqueConstraint("product_id", "captured_at", name="uq_product_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    product: Mapped[Product] = relationship(back_populates="prices")  # type: ignore


# Per-user preferences
class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    primary_store_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stores.id", ondelete="SET NULL"), nullable=True)


class StoreScrapeConfig(Base):
    __tablename__ = "store_scrape_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), unique=True, index=True)
    # Comma-separated list pages to crawl
    list_pages: Mapped[str] = mapped_column(Text, default="")
    product_link_selector: Mapped[str] = mapped_column(String(300), default="a[href]")
    title_selector: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    price_selector_override: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    # Optional regex hints
    model_regex: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    capacity_regex: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    color_regex: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
