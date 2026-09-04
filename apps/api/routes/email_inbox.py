from fastapi import APIRouter, Depends

from apps.api.dependencies.security import require_admin_auth
from services.channel_service.email_inbox_poller import EmailInboxPoller

router = APIRouter(prefix="/admin/email-inbox", tags=["admin"], dependencies=[Depends(require_admin_auth)])

_poller: EmailInboxPoller | None = None


def get_poller() -> EmailInboxPoller:
    global _poller
    if _poller is None:
        _poller = EmailInboxPoller()
    return _poller


def set_poller(p: EmailInboxPoller) -> None:
    global _poller
    _poller = p


@router.get("/status")
def email_inbox_status() -> dict:
    return get_poller().status()


@router.post("/poll")
def email_inbox_poll_now() -> dict:
    from apps.api.routes.webhooks import handle_email_message
    poller = get_poller()
    count = poller.poll_once(handle_email_message)
    return {"emails_processed_this_poll": count, **poller.status()}
