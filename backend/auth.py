"""JWT cookie authentication. Demo identity headers work only when explicitly enabled."""

import os
import secrets
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlmodel import Session, select

from database import get_session, utc_now
from models import AuthSession, User

COOKIE_NAME = "neighloop_session"
TOKEN_DAYS = 7
JWT_SECRET = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(48)
if os.getenv("ENVIRONMENT") == "production" and not os.getenv("JWT_SECRET_KEY"):
    raise RuntimeError("JWT_SECRET_KEY must be configured in production")
PASSWORD_HASHER = PasswordHasher()


def demo_mode() -> bool:
    return os.getenv("ENVIRONMENT") != "production" and os.getenv("NEIGHLOOP_DEMO_MODE", "false").lower() == "true"


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerificationError, ValueError):
        return False


def issue_token(session: Session, user: User) -> str:
    now = utc_now()
    expires = now + timedelta(days=TOKEN_DAYS)
    jti = secrets.token_urlsafe(24)
    session.add(AuthSession(user_id=user.id, jti=jti, expires_at=expires))
    session.commit()
    return jwt.encode({"sub": str(user.id), "jti": jti, "iat": now, "exp": expires}, JWT_SECRET,
                      algorithm="HS256")


def optional_current_user(
    session: Session = Depends(get_session),
    token_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    authorization: str | None = Header(default=None),
    x_demo_user_id: int | None = Header(default=None),
) -> User | None:
    bearer = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else None
    token = bearer or token_cookie
    if token:
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            jti = str(payload["jti"])
            user_id = int(payload["sub"])
        except (jwt.PyJWTError, ValueError, KeyError):
            if bearer:
                raise HTTPException(401, "登录已过期，请重新登录") from None
            return None
        active = session.exec(select(AuthSession).where(AuthSession.jti == jti,
                           AuthSession.user_id == user_id, AuthSession.revoked_at == None)).first()  # noqa: E711
        user = session.get(User, user_id)
        if not active or not user:
            if bearer:
                raise HTTPException(401, "登录已失效，请重新登录")
            return None
        return user
    if demo_mode() and x_demo_user_id is not None:
        user = session.get(User, x_demo_user_id)
        if user and user.email is None:
            return user
    return None


def current_user(request: Request, user: User | None = Depends(optional_current_user)) -> User:
    if not user:
        raise HTTPException(401, "请先登录")
    if user.email and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("X-NeighLoop-Request") != "1":
            raise HTTPException(403, "缺少受保护的请求标记")
    return user


def revoke_token(session: Session, token: str | None) -> None:
    if not token:
        return
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False})
        record = session.exec(select(AuthSession).where(AuthSession.jti == str(payload["jti"]))).first()
    except (jwt.PyJWTError, KeyError):
        return
    if record and record.revoked_at is None:
        record.revoked_at = utc_now()
        session.add(record)
        session.commit()
