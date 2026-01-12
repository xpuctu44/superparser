from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # seed companies
    with SessionLocal() as db:
        from sqlalchemy import select
        from .models import Company
        existing = {c.name for c in db.scalars(select(Company))}
        changed = False
        for name in ("Goodmi", "Максмобайлс"):
            if name not in existing:
                db.add(Company(name=name))
                changed = True
        if changed:
            db.commit()

