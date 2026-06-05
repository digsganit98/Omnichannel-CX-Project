import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["auth"])

_TOKEN_TTL_HOURS = 8


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int  # seconds


class VerifyResponse(BaseModel):
    valid: bool
    username: str


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    expected_user = os.getenv("ANALYTICS_USERNAME", "admin")
    expected_pass = os.getenv("ANALYTICS_PASSWORD", "")
    secret = os.getenv("JWT_SECRET")

    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")

    user_ok = hmac.compare_digest(body.username, expected_user)
    pass_ok = hmac.compare_digest(body.password, expected_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    exp = datetime.now(tz=timezone.utc) + timedelta(hours=_TOKEN_TTL_HOURS)
    payload = {"sub": body.username, "role": "analytics", "exp": exp}
    token = jwt.encode(payload, secret, algorithm="HS256")
    return LoginResponse(token=token, expires_in=_TOKEN_TTL_HOURS * 3600)
