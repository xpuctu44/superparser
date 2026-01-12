from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path
from .deps import get_session
from .auth import hash_password, verify_password, create_session_token, get_user_by_email, get_user_by_identifier
from .models import User, Company
from sqlalchemy import select


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html", "xml"]))


router = APIRouter(prefix="/auth")


@router.get("/login", response_class=HTMLResponse)
def login_form():
    tmpl = env.get_template("auth_login.html")
    return tmpl.render()


@router.post("/login")
def login(
    identifier: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_session),
):
    user = get_user_by_identifier(db, identifier)
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="Неверные email или пароль")
    token = create_session_token(user.id)
    resp = RedirectResponse("/compare", status_code=303)
    resp.set_cookie("session", token, httponly=True, samesite="lax")
    return resp


@router.get("/signup", response_class=HTMLResponse)
def signup_form(db: Session = Depends(get_session)):
    companies = list(db.scalars(select(Company)))
    if not companies:
        # Fallback seed if startup seeding hasn't run yet
        db.add_all([Company(name="Goodmi"), Company(name="Максмобайлс")])
        db.commit()
        companies = list(db.scalars(select(Company)))
    tmpl = env.get_template("auth_signup.html")
    return tmpl.render(companies=companies)


@router.post("/signup")
def signup(
    email: str = Form(...),
    username: str = Form(""),
    phone: str = Form(""),
    company_id: int = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_session),
):
    if get_user_by_email(db, email):
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    user = User(email=email, username=username or None, phone=phone or None, company_id=company_id, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_session_token(user.id)
    resp = RedirectResponse("/compare", status_code=303)
    resp.set_cookie("session", token, httponly=True, samesite="lax")
    return resp


@router.post("/logout")
def logout():
    resp = RedirectResponse("/auth/login", status_code=303)
    resp.delete_cookie("session")
    return resp

