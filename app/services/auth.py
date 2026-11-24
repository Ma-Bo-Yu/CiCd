"""本地用户名密码认证与会话依赖。"""

from __future__ import annotations

from urllib.parse import quote

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User

SESSION_USER_KEY = "user_id"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def get_user_by_id(db: Session, user_id: str | None) -> User | None:
    if not user_id:
        return None
    return db.get(User, user_id)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username.strip()))


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    return get_user_by_id(db, request.session.get(SESSION_USER_KEY))


def login_user(request: Request, user: User) -> None:
    request.session[SESSION_USER_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """页面依赖：未登录则 303 跳转登录页。"""
    user = get_optional_user(request, db)
    if user is not None:
        return user
    next_path = request.url.path
    if request.url.query:
        next_path = f"{next_path}?{request.url.query}"
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": f"/login?next={quote(next_path, safe='')}"},
    )


def require_user_api(request: Request, db: Session = Depends(get_db)) -> User:
    """API 依赖：未登录返回 401 JSON。"""
    user = get_optional_user(request, db)
    if user is not None:
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": {"code": "unauthorized", "message": "请先登录"}},
    )
