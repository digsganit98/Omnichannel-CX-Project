import os
import smtplib
from email.message import EmailMessage
from typing import Any


class SMTPEmailConnector:
    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST", "localhost")
        self.port = int(os.getenv("SMTP_PORT", "1025"))
        self.from_email = os.getenv("SMTP_FROM_EMAIL", "support@example.com")
        self.username = os.getenv("SMTP_USERNAME")
        self.password = os.getenv("SMTP_PASSWORD")
        self.use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
        self.use_ssl = os.getenv("SMTP_USE_SSL", "false").lower() == "true"

    def status(self) -> dict[str, Any]:
        return {
            "provider": "smtp",
            "host": self.host,
            "port": self.port,
            "from_email": self.from_email,
            "username_configured": bool(self.username),
            "password_configured": bool(self.password),
            "use_tls": self.use_tls,
            "use_ssl": self.use_ssl,
            "gmail_ready": self.host in {"smtp.gmail.com", "gmail-smtp-in.l.google.com"}
            and self.port in {465, 587}
            and bool(self.username)
            and bool(self.password)
            and (self.use_tls or self.use_ssl),
        }

    def send_text(self, to: str, subject: str, text: str) -> dict:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = f"Re: {subject or 'Customer support request'}"
        message.set_content(text)
        client_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with client_class(self.host, self.port, timeout=15) as client:
            if not self.use_ssl:
                client.ehlo()
            if self.use_tls:
                client.starttls()
                client.ehlo()
            if self.username:
                client.login(self.username, self.password or "")
            response = client.send_message(message)
        return {"status": "sent", "provider": "smtp", "host": self.host, "refused_recipients": response}
