import hashlib
import hmac
import os
import time

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_auth

router = APIRouter(tags=["admin-auth"])

_TOKEN_TTL_SECONDS = 86400  # 24 hours


def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    parts = stored.split(":", 1)
    if len(parts) != 2:
        return False
    salt, expected = parts
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return hmac.compare_digest(actual, expected)


def _make_admin_token(username: str, email: str) -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    payload = {
        "sub": username,
        "email": email,
        "role": "admin_user",
        "exp": int(time.time()) + _TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


class VerifyKeyRequest(BaseModel):
    api_key: str


class SignupRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/admin/auth/verify-key")
def verify_key(req: VerifyKeyRequest):
    expected = os.getenv("ADMIN_API_KEY", "")
    if not expected or not hmac.compare_digest(req.api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid admin API key")
    return {"valid": True}


@router.post("/admin/auth/signup")
def admin_signup(req: SignupRequest):
    # No admin key: it gated the ability to CREATE the first account behind already having
    # the credential that account was meant to replace. Signup stays open - a deliberate
    # demo choice, not an oversight; close it by seeding the first account and removing
    # this route if this is ever exposed beyond a local stack.
    if not req.username or len(req.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if not req.password or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    if not req.email or "@" not in req.email:
        raise HTTPException(status_code=400, detail="Invalid email address")

    repo = get_repository()
    if repo.get_admin_user_by_username(req.username):
        raise HTTPException(status_code=409, detail="Username already taken")
    if repo.get_admin_user_by_email(req.email):
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = _hash_password(req.password)
    user = repo.create_admin_user(req.username, req.email, password_hash)
    token = _make_admin_token(req.username, req.email)
    return {"token": token, "expires_in": _TOKEN_TTL_SECONDS, "user": user}


@router.post("/admin/auth/login")
def admin_login(req: LoginRequest):
    repo = get_repository()
    user = repo.get_admin_user_by_username(req.username)
    if not user or not _verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = _make_admin_token(user["username"], user["email"])
    user_public = {k: v for k, v in user.items() if k != "password_hash"}
    return {"token": token, "expires_in": _TOKEN_TTL_SECONDS, "user": user_public}


@router.get("/admin/auth/users", dependencies=[Depends(require_admin_auth)])
def list_admin_users():
    repo = get_repository()
    return repo.list_admin_users()


class ChangePasswordRequest(BaseModel):
    username: str
    new_password: str


@router.post("/admin/auth/change-password", dependencies=[Depends(require_admin_auth)])
def change_password(
    req: ChangePasswordRequest,
    authorization: str | None = Header(default=None),
):
    if not req.new_password or len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    repo = get_repository()
    user = repo.get_admin_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_hash = _hash_password(req.new_password)
    with repo.connection() as conn:
        conn.execute(
            "UPDATE admin_users SET password_hash = ? WHERE username = ?",
            (new_hash, req.username),
        )
    return {"updated": True}
