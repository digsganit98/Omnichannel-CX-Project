from fastapi import APIRouter, Depends
from pydantic import BaseModel

from apps.api.dependencies.security import require_admin_key
from services.channel_service.connectors.email_sender import SMTPEmailConnector

router = APIRouter(prefix="/admin/email", tags=["admin"], dependencies=[Depends(require_admin_key)])


class EmailTestSend(BaseModel):
    to: str
    subject: str = "Omnichannel CX Gmail SMTP test"
    body: str = "This is a test email from the Omnichannel CX Accelerator."


@router.get("/status")
def email_status() -> dict:
    return SMTPEmailConnector().status()


@router.post("/test-send")
def test_email_send(payload: EmailTestSend) -> dict:
    return SMTPEmailConnector().send_text(payload.to, payload.subject, payload.body)
