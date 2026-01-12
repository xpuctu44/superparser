from __future__ import annotations

from typing import Optional
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import Request
from .config import settings
from .models import User
from sqlalchemy.orm import Session
from sqlalchemy import select


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
serializer = URLSafeSerializer(settings.secret_key, salt="session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_session_token(user_id: int) -> str:
    return serializer.dumps({"uid": user_id})


def parse_session_token(token: str) -> Optional[int]:
    try:
        data = serializer.loads(token)
        return int(data.get("uid"))
    except (BadSignature, ValueError, TypeError):
        return None


def get_current_user(request: Request, db: Session) -> Optional[User]:
    token = request.cookies.get("session")
    if not token:
        return None
    user_id = parse_session_token(token)
    if not user_id:
        return None
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email))


def get_user_by_identifier(db: Session, identifier: str) -> Optional[User]:
    # identifier can be email or username
    stmt = select(User).where((User.email == identifier) | (User.username == identifier))
    return db.scalar(stmt)

