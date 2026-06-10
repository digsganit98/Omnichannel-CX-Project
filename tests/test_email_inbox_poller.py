from email.message import EmailMessage

from services.channel_service.email_inbox_poller import EmailInboxPoller


class FakeIMAP:
    def __init__(self, raw_message: bytes):
        self.raw_message = raw_message
        self.stored = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def login(self, username, password):
        return "OK", []

    def select(self, mailbox, readonly=False):
        return "OK", []

    def search(self, charset, criterion):
        return "OK", [b"1"]

    def fetch(self, num, query):
        return "OK", [(b"1", self.raw_message)]

    def store(self, num, operation, flag):
        self.stored.append((num, operation, flag))
        return "OK", []


def _message() -> bytes:
    msg = EmailMessage()
    msg["From"] = "Customer Name <customer@example.com>"
    msg["To"] = "support@example.com"
    msg["Subject"] = "Account query"
    msg["Message-ID"] = "<email-poller-test@example.com>"
    msg.set_content("Please help with my account.")
    return msg.as_bytes()


def _configured_poller(monkeypatch) -> EmailInboxPoller:
    monkeypatch.setenv("IMAP_USERNAME", "support@example.com")
    monkeypatch.setenv("IMAP_PASSWORD", "app-password")
    return EmailInboxPoller()


def test_marks_email_seen_only_after_successful_handler(monkeypatch):
    fake = FakeIMAP(_message())
    monkeypatch.setattr(
        "services.channel_service.email_inbox_poller.imaplib.IMAP4_SSL",
        lambda *args, **kwargs: fake,
    )
    poller = _configured_poller(monkeypatch)
    received = []

    count = poller.poll_once(received.append)

    assert count == 1
    assert received[0].from_email == "customer@example.com"
    assert fake.stored == [(b"1", "+FLAGS", "\\Seen")]
    assert poller.status()["emails_processed"] == 1


def test_keeps_email_unseen_when_handler_fails(monkeypatch):
    fake = FakeIMAP(_message())
    monkeypatch.setattr(
        "services.channel_service.email_inbox_poller.imaplib.IMAP4_SSL",
        lambda *args, **kwargs: fake,
    )
    poller = _configured_poller(monkeypatch)

    def fail(_payload):
        raise RuntimeError("persistence unavailable")

    count = poller.poll_once(fail)

    assert count == 0
    assert fake.stored == []


def test_rejects_overlapping_poll(monkeypatch):
    poller = _configured_poller(monkeypatch)
    poller._poll_lock.acquire()
    try:
        assert poller.poll_once(lambda _payload: None) == 0
        assert poller.status()["polling"] is True
    finally:
        poller._poll_lock.release()
