import email
import imaplib
import logging
import os
import re
from email.header import decode_header as _decode_header

logger = logging.getLogger(__name__)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = _decode_header(value)
    decoded = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(chunk)
    return " ".join(decoded).strip()


def _plain_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            if ct == "text/plain" and part.get("Content-Disposition") != "attachment":
                raw = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return raw.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                raw = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                text = raw.decode(charset, errors="replace")
                return re.sub(r"<[^>]+>", " ", text).strip()
    else:
        raw = msg.get_payload(decode=True)
        if raw:
            charset = msg.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
    return ""


def _extract_address(header_value: str) -> str:
    match = re.search(r"<([^>]+)>", header_value)
    return match.group(1).strip() if match else header_value.strip()


class IMAPEmailReader:
    def __init__(self) -> None:
        self.host = os.getenv("IMAP_HOST", "imap.gmail.com")
        self.port = int(os.getenv("IMAP_PORT", "993"))
        self.username = os.getenv("IMAP_USERNAME", "")
        self.password = os.getenv("IMAP_PASSWORD", "")

    def _connect(self) -> imaplib.IMAP4_SSL:
        client = imaplib.IMAP4_SSL(self.host, self.port)
        client.login(self.username, self.password)
        client.select("INBOX")
        return client

    def fetch_unseen(self) -> list[dict]:
        results: list[dict] = []
        try:
            client = self._connect()
            _, data = client.search(None, "UNSEEN")
            uids = data[0].split()
            if not uids:
                client.logout()
                return results
            for uid in uids:
                try:
                    _, msg_data = client.fetch(uid, "(RFC822)")
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)
                    from_raw = _decode(msg.get("From", ""))
                    from_email = _extract_address(from_raw)
                    subject = _decode(msg.get("Subject", "(no subject)"))
                    message_id = (msg.get("Message-ID") or "").strip()
                    body = _plain_body(msg)
                    # mark seen before yielding so a crash never re-processes
                    client.store(uid, "+FLAGS", "\\Seen")
                    results.append({
                        "from_email": from_email,
                        "subject": subject,
                        "body": body,
                        "message_id": message_id,
                        "metadata": {"provider": "imap", "uid": uid.decode()},
                    })
                    logger.info("imap_email_fetched", extra={"from": from_email, "subject": subject})
                except Exception:
                    logger.exception("imap_single_fetch_failed", extra={"uid": uid})
            client.logout()
        except Exception:
            logger.exception("imap_connection_failed")
        return results
