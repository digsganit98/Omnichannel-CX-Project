import hashlib
import hmac
import os

from fastapi import Header, HTTPException


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("ADMIN_API_KEY")
    if not expected or not x_admin_key or not hmac.compare_digest(x_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid admin API key")


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
