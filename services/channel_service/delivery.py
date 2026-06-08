import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

from services.channel_adapter import ChannelAdapterRegistry, OutboundMessage
from services.channel_service.connectors.email_sender import SMTPEmailConnector
from services.channel_service.connectors.whatsapp_cloud import LocalWhatsAppTestConnector
from shared.schemas.messages import Channel, InboundMessage

logger = logging.getLogger(__name__)


class OutboundDeliveryService:
    def __init__(self, whatsapp=None, email=None, retries: int = 3) -> None:
        self.whatsapp = whatsapp
        self.email = email
        self.retries = retries

    def send(self, message: InboundMessage, text: str) -> dict:
        if (
            os.getenv("OUTBOUND_DELIVERY_MODE", "log") == "log"
            and message.provider != "whatsapp_local_test"
            and message.metadata.get("outbound_provider") != "meta"
            and not (self.whatsapp or self.email)
        ):
            logger.info("outbound_local_delivery", extra={"channel": message.channel.value, "message_id": message.external_message_id})
            return {"status": "sent", "provider": "local_log"}
        connector = self._connector(message)
        for attempt in range(1, self.retries + 1):
            try:
                if message.channel == Channel.WHATSAPP and connector is None:
                    adapter = ChannelAdapterRegistry.get(message.channel)
                    result = _run_async(adapter.send_outbound(OutboundMessage(to_id=message.channel_identifier, text=text)))
                elif message.channel == Channel.WHATSAPP:
                    result = connector.send_text(message.channel_identifier, text)
                else:
                    result = connector.send_text(
                        message.channel_identifier,
                        message.subject or "",
                        text,
                        reply_to_message_id=message.external_message_id,
                    )
                return {"status": "sent", "attempts": attempt, "provider_response": result}
            except Exception as exc:
                logger.exception("outbound_delivery_failed", extra={"channel": message.channel.value, "attempt": attempt})
                if attempt == self.retries:
                    return {"status": "failed", "attempts": attempt, "error": str(exc)}
                time.sleep(0.1 * attempt)
        return {"status": "failed", "error": "delivery exhausted"}

    def _connector(self, message: InboundMessage):
        if message.channel == Channel.WHATSAPP and message.provider == "whatsapp_local_test":
            return LocalWhatsAppTestConnector()
        if message.channel == Channel.WHATSAPP:
            return self.whatsapp
        return self.email or SMTPEmailConnector()


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()
