import asyncio
import logging
import os

logger = logging.getLogger(__name__)


async def run_email_poller(poller=None) -> None:
    if poller is None:
        from services.channel_service.email_inbox_poller import EmailInboxPoller
        poller = EmailInboxPoller()
    interval = int(os.getenv("IMAP_POLL_INTERVAL_SECONDS", "30"))
    loop = asyncio.get_event_loop()
    logger.info("email_poller_started", extra={"interval_seconds": interval})
    while True:
        try:
            # Run in thread pool so it never blocks the uvicorn event loop
            await loop.run_in_executor(None, _poll_once, poller)
        except Exception:
            logger.exception("email_poller_cycle_failed")
        await asyncio.sleep(interval)


def _poll_once(poller=None) -> int:
    from apps.api.routes.webhooks import handle_email_message
    if poller is None:
        from services.channel_service.email_inbox_poller import EmailInboxPoller
        poller = EmailInboxPoller()
    return poller.poll_once(handle_email_message)
