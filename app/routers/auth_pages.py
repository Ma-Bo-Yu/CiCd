from urllib.parse import unquote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.services.auth import (
    get_optional_user,
    get_user_by_username,
    hash_password,
    login_user,
    logout_user,
    verify_password,
)

router = APIRouter(tags=["auth"])

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


def _auth_context(**extra):
    return {"current_user": None, **extra}


def _safe_next(next_url: str | None) -> str:
    if not next_url:
        return "/"
    decoded = unquote(next_url).strip()
    if not decoded.startswith("/") or decoded.startswith("//"):
        return "/"
    if decoded.startswith("/login") or decoded.startswith("/register"):
        return "/"
    return decoded


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db), next: str | None = None):
    if get_optional_user(request, db):
        return RedirectResponse(url=_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context=_auth_context(
            page_title="登录", error=None, next=next or "/", username=""
        ),
    )


@router.post("/login")
def login_submit(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    user = get_user_by_username(db, username)
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context=_auth_context(
                page_title="登录",
                error="用户名或密码错误",
                next=next,
                username=username.strip(),
            ),
            status_code=400,
        )
    login_user(request, user)
    return RedirectResponse(url=_safe_next(next), status_code=303)


@router.get("/register")
def register_page(request: Request, db: Session = Depends(get_db)):
    if get_optional_user(request, db):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context=_auth_context(page_title="注册", error=None, username=""),
    )


@router.post("/register")
def register_submit(
    request: Request,
    db: Session = Depends(get_db),
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    name = username.strip()
    error: str | None = None
    if len(name) < 3 or len(name) > 32:
        error = "用户名长度需为 3～32 个字符"
    elif not name.replace("_", "").isalnum():
        error = "用户名仅允许字母、数字和下划线"
    elif len(password) < 6:
        error = "密码至少 6 位"
    elif password != password_confirm:
        error = "两次输入的密码不一致"
    elif get_user_by_username(db, name) is not None:
        error = "用户名已被占用"

    if error:
        return templates.TemplateResponse(
            request=request,
            name="auth/register.html",
            context=_auth_context(page_title="注册", error=error, username=name),
            status_code=400,
        )

    from app.models.user import PLAN_FREE

    user = User(username=name, password_hash=hash_password(password), plan=PLAN_FREE)
    db.add(user)
    db.commit()
    db.refresh(user)
    login_user(request, user)
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/login", status_code=303)
