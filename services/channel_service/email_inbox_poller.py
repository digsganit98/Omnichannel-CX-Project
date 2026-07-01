import email as email_lib
import imaplib
import logging
import os
import time
from email.header import decode_header
from typing import Any, Callable, Optional

from shared.schemas.messages import EmailWebhookPayload
from shared.utils.ids import new_id

logger = logging.getLogger(__name__)


class EmailInboxPoller:
    """Poll a Gmail inbox via IMAP for new (UNSEEN) customer emails.

    Each unseen email is converted to EmailWebhookPayload and passed to the
    provided message_handler (the same handler used by the email webhook).
    Emails are marked as SEEN on the server after successful delivery to the
    handler, so they are not reprocessed on the next poll.
    """

    def __init__(self) -> None:
        self.host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self.port = int(os.getenv("IMAP_PORT", "993"))
        self.username = os.getenv("IMAP_USERNAME", "")
        self.password = os.getenv("IMAP_PASSWORD", "")
        self.mailbox = os.getenv("IMAP_MAILBOX", "INBOX")
        self.poll_interval = int(os.getenv("EMAIL_POLL_INTERVAL_SECONDS", "30"))
        self._last_poll_ts: Optional[float] = None
        self._emails_processed: int = 0
        self._last_error: Optional[str] = None

    def is_configured(self) -> bool:
        return bool(self.username and self.password)

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.is_configured(),
            "host": self.host,
            "port": self.port,
            "mailbox": self.mailbox,
            "poll_interval_seconds": self.poll_interval,
            "last_poll_ts": self._last_poll_ts,
            "emails_processed": self._emails_processed,
            "last_error": self._last_error,
        }

    def poll_once(self, message_handler: Callable[[EmailWebhookPayload], Any]) -> int:
        """Fetch UNSEEN emails, pass each to message_handler, return count processed."""
        if not self.is_configured():
            return 0
        try:
            count = 0
            with imaplib.IMAP4_SSL(self.host, self.port) as imap:
                imap.login(self.username, self.password)
                imap.select(self.mailbox, readonly=False)
                _, message_nums = imap.search(None, "UNSEEN")
                for num in message_nums[0].split():
                    _, msg_data = imap.fetch(num, "(RFC822)")
                    for response_part in msg_data:
                        if not isinstance(response_part, tuple):
                            continue
                        raw_msg = email_lib.message_from_bytes(response_part[1])
                        payload = self._build_payload(raw_msg)
                        if not payload:
                            continue
                        try:
                            message_handler(payload)
                            imap.store(num, "+FLAGS", "\\Seen")
                            count += 1
                            logger.info("email_inbox_processed", extra={"message_id": payload.message_id})
                        except Exception:
                            logger.exception("email_inbox_handler_failed", extra={"message_id": payload.message_id})
            self._emails_processed += count
            self._last_error = None
            self._last_poll_ts = time.time()
            logger.info("email_inbox_poll_done", extra={"count": count})
            return count
        except Exception as exc:
            self._last_error = str(exc)
            self._last_poll_ts = time.time()
            logger.exception("email_inbox_poll_error")
            return 0

    def _build_payload(self, msg) -> Optional[EmailWebhookPayload]:
        from_addr = self._decode_header_val(msg.get("From", ""))
        subject = self._decode_header_val(msg.get("Subject", "(no subject)"))
        message_id = (msg.get("Message-ID") or new_id("email")).strip()
        date_str = msg.get("Date", "")

        body = self._extract_text_body(msg)

        if not from_addr:
            return None

        return EmailWebhookPayload(
            from_email=from_addr,
            subject=subject,
            body=body.strip(),
            message_id=message_id,
            metadata={
                "provider": "gmail_imap",
                "date": date_str,
                "correlation_id": new_id("corr"),
            },
        )

    @staticmethod
    def _extract_text_body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        return part.get_payload(decode=True).decode(charset, errors="replace")
                    except Exception:
                        return str(part.get_payload())
            return ""
        charset = msg.get_content_charset() or "utf-8"
        try:
            return msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            return str(msg.get_payload())

    @staticmethod
    def _decode_header_val(raw: str) -> str:
        parts = decode_header(raw)
        out: list[str] = []
        for bval, charset in parts:
            if isinstance(bval, bytes):
                out.append(bval.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(str(bval))
        return "".join(out).strip()
