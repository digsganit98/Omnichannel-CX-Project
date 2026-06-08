import asyncio
import logging
import os
import re

logger = logging.getLogger(__name__)

# Senders whose emails should never be treated as customer support requests
_SKIP_PATTERNS = re.compile(
    r"(noreply|no-reply|mailer-daemon|notifications?@|donotreply|"
    r"@accounts\.google\.com|@notifications\.google\.com|"
    r"@google\.com|@googlemail\.com|automated|bounce|postmaster)",
    re.IGNORECASE,
)

_MAX_PER_CYCLE = int(os.getenv("IMAP_MAX_PER_CYCLE", "5"))
_SUPPORT_EMAIL = os.getenv("IMAP_USERNAME", "").lower()


def _should_skip(from_email: str) -> bool:
    addr = from_email.lower()
    if _SUPPORT_EMAIL and addr == _SUPPORT_EMAIL:
        return True
    return bool(_SKIP_PATTERNS.search(addr))


async def run_email_poller() -> None:
    interval = int(os.getenv("IMAP_POLL_INTERVAL_SECONDS", "30"))
    loop = asyncio.get_event_loop()
    logger.info("email_poller_started", extra={"interval_seconds": interval})
    while True:
        try:
            # Run in thread pool so it never blocks the uvicorn event loop
            await loop.run_in_executor(None, _poll_once)
        except Exception:
            logger.exception("email_poller_cycle_failed")
        await asyncio.sleep(interval)


def _poll_once() -> None:
    from services.channel_service.connectors.imap_reader import IMAPEmailReader
    from apps.api.routes.webhooks import handle_email_message
    from shared.schemas.messages import EmailWebhookPayload

    reader = IMAPEmailReader()
    emails = reader.fetch_unseen()

    processed = 0
    for e in emails:
        if _should_skip(e["from_email"]):
            logger.info("email_poller_skipped", extra={"from": e["from_email"], "reason": "automated_sender"})
            continue
        if processed >= _MAX_PER_CYCLE:
            logger.info("email_poller_cycle_limit_reached", extra={"limit": _MAX_PER_CYCLE})
            break
        try:
            payload = EmailWebhookPayload(
                from_email=e["from_email"],
                subject=e["subject"],
                body=e["body"],
                message_id=e["message_id"],
                metadata=e["metadata"],
            )
            handle_email_message(payload)
            processed += 1
            logger.info("email_poller_processed", extra={"from": e["from_email"], "subject": e["subject"]})
        except Exception:
            logger.exception("email_poller_process_failed", extra={"from": e.get("from_email")})
