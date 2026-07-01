import hmac
import os

import jwt
from fastapi import Header, HTTPException


def require_analytics_token(authorization: str | None = Header(default=None)) -> dict:
    """Accept JWT Bearer token (used by standalone analytics-ui)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ")
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_analytics_access(
    authorization: str | None = Header(default=None),
    x_admin_key: str | None = Header(default=None),
) -> dict:
    """Accept either x-admin-key (admin-ui) or JWT Bearer token (standalone analytics-ui)."""
    expected_key = os.getenv("ADMIN_API_KEY")
    if x_admin_key and expected_key and hmac.compare_digest(x_admin_key, expected_key):
        return {"sub": "admin", "role": "admin"}
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
        secret = os.getenv("JWT_SECRET")
        if secret:
            try:
                return jwt.decode(token, secret, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                raise HTTPException(status_code=401, detail="Token expired")
            except jwt.InvalidTokenError:
                pass
    raise HTTPException(status_code=401, detail="Authentication required — provide x-admin-key or Bearer token")
