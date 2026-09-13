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

    # WHAT ACTUALLY HAPPENED to the message, reported separately from `status`.
    #
    # `status` stays "sent"/"failed" because eleven test assertions and six production
    # readers compare it to "sent" - graph.py:793 audits the turn as `outbound_failed` on
    # anything else, so redefining that value would mark every real delivery a failure.
    # `delivery_mode` is therefore ADDITIVE: nothing that reads `status` changes behaviour,
    # and anything that wants the truth now has it.
    #
    # The three modes were indistinguishable before, which is the trap recorded in
    # docs/rules_to_follow/ec2-operations.md § 8: "a Meta rejection, a local-log fallback
    # and a real delivery are indistinguishable on screen. The only way to know is the
    # container log or the recipient's phone."
    DELIVERED = "delivered"        # a provider accepted it
    PORTAL = "portal"              # persisted for the web portal to poll - no provider exists
    LOGGED_ONLY = "logged_only"    # written to the log and nowhere else; NOBODY received it
    FAILED = "failed"              # a provider was tried and refused it

    def send(self, message: InboundMessage, text: str) -> dict:
        if message.channel == Channel.WEB_CHAT:
            # Web chat replies are returned synchronously in the HTTP response body
            # (apps/api/routes/web_chat.py) — there is no outbound provider to push to.
            # Without this branch, _connector()'s email fallback would attempt an SMTP
            # send to a bogus "web_session:<uuid>" address whenever SMTP is configured.
            # This is a genuine delivery: the customer reads it in the portal off the
            # persisted turn. It is called PORTAL rather than DELIVERED because no
            # provider acknowledged anything, so there is nothing to chase if it is missed.
            return {"status": "sent", "provider": "web_chat_sync", "delivery_mode": self.PORTAL}
        if (
            os.getenv("OUTBOUND_DELIVERY_MODE", "log") == "log"
            and message.provider != "whatsapp_local_test"
            and message.metadata.get("outbound_provider") != "meta"
            and not (self.whatsapp or self.email)
        ):
            logger.info("outbound_local_delivery", extra={"channel": message.channel.value, "message_id": message.external_message_id})
            # NOT a delivery. The message went to the container log and no further. Reported
            # as "sent" for the readers above, but delivery_mode says plainly that the
            # customer received nothing.
            return {"status": "sent", "provider": "local_log", "delivery_mode": self.LOGGED_ONLY}
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
                return {"status": "sent", "attempts": attempt, "provider_response": result,
                        "delivery_mode": self.DELIVERED}
            except Exception as exc:
                logger.exception("outbound_delivery_failed", extra={"channel": message.channel.value, "attempt": attempt})
                if attempt == self.retries:
                    return {"status": "failed", "attempts": attempt, "error": str(exc),
                            "delivery_mode": self.FAILED}
                time.sleep(0.1 * attempt)
        return {"status": "failed", "error": "delivery exhausted", "delivery_mode": self.FAILED}

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
