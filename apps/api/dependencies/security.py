import hashlib
import hmac
import os

import jwt
from fastapi import Header, HTTPException


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ADMIN_API_KEY")
    if not expected or not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid admin API key")


def require_admin_auth(
    authorization: str | None = Header(default=None),
    x_admin_key: str | None = Header(default=None),
) -> dict:
    """Admin access via a signed-in session OR the raw API key.

    The console used to authenticate by making the operator paste ADMIN_API_KEY, so the key
    was both the credential and the login step - and because /admin/auth/login itself sat
    behind the key, an account could not be created without already holding it. Signing in
    now issues the JWT that `_make_admin_token` was already minting, and this accepts it.

    `x_admin_key` is still accepted deliberately. It is how the runbook, the fresh-start
    checklist and every documented `Invoke-RestMethod` example authenticate; dropping it
    would break automation to remove a header no human types. What changes is that a PERSON
    no longer needs the key, not that scripts lose it.

    Mirrors `jwt_auth.require_analytics_access`, which already accepts either credential -
    same shape, so there is one way this app answers "is this caller an admin".
    """
    expected_key = os.getenv("ADMIN_API_KEY")
    if x_admin_key and expected_key and hmac.compare_digest(x_admin_key, expected_key):
        return {"sub": "admin", "role": "admin"}

    if authorization and authorization.startswith("Bearer "):
        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise HTTPException(status_code=503, detail="JWT_SECRET is not configured")
        try:
            return jwt.decode(
                authorization.removeprefix("Bearer "), secret, algorithms=["HS256"]
            )
        except jwt.ExpiredSignatureError:
            # Distinct from "invalid": the console reads this to send the operator back to
            # the sign-in screen rather than showing a wall of failed panels.
            raise HTTPException(status_code=401, detail="Session expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid session token")

    raise HTTPException(status_code=401, detail="Authentication required")


def validate_whatsapp_signature(body: bytes, signature: str | None) -> None:
    secret = os.getenv("WHATSAPP_APP_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="WHATSAPP_APP_SECRET is not configured")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid WhatsApp signature")


def validate_local_whatsapp_test_signature(signature: str | None) -> None:
    if os.getenv("WHATSAPP_LOCAL_TEST_MODE", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Local WhatsApp test mode is disabled")
    expected = os.getenv("WHATSAPP_TEST_SIGNATURE")
    if not expected or not signature or not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid local WhatsApp test signature")


def validate_email_secret(secret: str | None) -> None:
    expected = os.getenv("EMAIL_WEBHOOK_SECRET")
    if not expected or not secret or not hmac.compare_digest(secret, expected):
        raise HTTPException(status_code=401, detail="Invalid email webhook secret")
