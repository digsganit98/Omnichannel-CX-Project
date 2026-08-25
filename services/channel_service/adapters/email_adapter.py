import re

from shared.schemas.messages import Channel, EmailWebhookPayload, InboundMessage
from shared.utils.ids import new_id

from .base import ChannelAdapter

# An email reply carries the ENTIRE previous thread quoted beneath it, and every
# downstream step (resolution detection, intent classification, ticket scope) reads
# the message as one flat string. That let OUR OWN outbound text act as customer
# input: "monitoring each case closely" supplied "close" and the signature "Thank
# you for reaching out" supplied "thank you", which together satisfied the ticket
# resolution detector and closed a ticket the customer had only asked about.
# Cut at the first quote marker so only what the customer typed enters the pipeline.
_ATTRIBUTION = re.compile(
    r"^\s*On\b[\s\S]{0,300}?\bwrote\s*:\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_SEPARATOR = re.compile(
    r"^\s*(-{2,}\s*Original Message\s*-{2,}"
    r"|_{5,}"
    r"|From:\s.+"
    r"|Sent from my \w+)\s*$",
    re.IGNORECASE,
)


def strip_quoted_reply(body: str) -> str:
    """Return only the text the sender typed, dropping the quoted thread below it.

    Gmail wraps its "On <date> ... wrote:" attribution across lines and puts a narrow
    no-break space in the timestamp, so the attribution is matched across lines rather
    than as a single-line pattern. If stripping would leave nothing (a reply that is
    only quoted text), the original is kept - an empty message would lose the turn
    entirely, which is worse than an over-long one.
    """
    if not body:
        return body
    text = body.replace("\r\n", "\n")
    cut = None
    match = _ATTRIBUTION.search(text)
    if match:
        cut = match.start()
    offset = 0
    for line in text.split("\n"):
        if line.lstrip().startswith(">") or _SEPARATOR.match(line):
            cut = offset if cut is None else min(cut, offset)
            break
        offset += len(line) + 1
    stripped = (text if cut is None else text[:cut]).strip()
    return stripped or body.strip()


class EmailAdapter(ChannelAdapter):
    def normalize(self, payload: EmailWebhookPayload) -> InboundMessage:
        text = f"{payload.subject}\n\n{strip_quoted_reply(payload.body)}".strip()
        return InboundMessage(
            channel=Channel.EMAIL,
            channel_identifier=payload.from_email.strip().lower(),
            display_name=payload.from_email,
            subject=payload.subject,
            text=text,
            provider=str(payload.metadata.get("provider", "email")),
            external_message_id=payload.message_id,
            correlation_id=str(payload.metadata.get("correlation_id") or new_id("corr")),
            metadata=payload.metadata,
            profile_metadata={"email": payload.from_email.strip().lower()},
        )
