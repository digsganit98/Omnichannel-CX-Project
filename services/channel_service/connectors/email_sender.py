import os
import smtplib
from email.message import EmailMessage


class SMTPEmailConnector:
    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST", "localhost")
        self.port = int(os.getenv("SMTP_PORT", "1025"))
        self.from_email = os.getenv("SMTP_FROM_EMAIL", "support@example.com")
        self.username = os.getenv("SMTP_USERNAME")
        self.password = os.getenv("SMTP_PASSWORD")
        self.use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"

    def send_text(self, to: str, subject: str, text: str) -> dict:
        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to
        message["Subject"] = f"Re: {subject or 'Customer support request'}"
        message.set_content(text)
        with smtplib.SMTP(self.host, self.port, timeout=15) as client:
            if self.use_tls:
                client.starttls()
            if self.username:
                client.login(self.username, self.password or "")
            client.send_message(message)
        return {"status": "sent", "provider": "smtp"}
