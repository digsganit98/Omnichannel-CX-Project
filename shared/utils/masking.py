"""PII masking helpers for customer-facing replies, citations, and persisted evidence.

These are OUTPUT-layer helpers: they make a *displayed* value deliberately
incomplete (e.g. show last 4 digits only). They are NOT encryption — encryption
protects data at rest and is reversible; masking is a one-way redaction applied
right before a value is shown to a customer or written to a log / citation.

Intended call sites (when the data exists): the answer-formatting functions that
build customer-facing strings for account / card / transaction intents — i.e. mask
the value *before* it is placed in a reply, a RAG context, retrieval_evidence, or
handed to the LLM, so the model never even receives the full number.

IMPORTANT — do NOT mask everything indiscriminately:
  - loan / claim / policy IDs and amounts are the *answer* a verified customer asked
    for (loan_status, claim_status, policy_status). Masking those breaks the product.
  - customer_id, ticket IDs and intents are internal references, not PII.
Only the functions below — for account numbers, cards, PAN, phone, email — are PII.

Every function is defensive: empty / None / too-short input returns a safe fully
masked value and never raises, because these run on the reply path where an
exception would mean a failed customer response.
"""

import re

ACCOUNT_MASK_CHAR = "X"
CARD_MASK_CHAR = "*"
PHONE_MASK_CHAR = "*"


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def mask_account(account_no: str | None) -> str:
    """Mask a bank account number, keeping the last 4 digits.

    '50100123456789' -> 'XXXXXX6789'. Short/empty input -> fully masked or ''.
    """
    s = (str(account_no) if account_no is not None else "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return ACCOUNT_MASK_CHAR * len(s)
    return ACCOUNT_MASK_CHAR * (len(s) - 4) + s[-4:]


def mask_card(card_no: str | None) -> str:
    """Mask a card number to last 4 digits, grouped (PCI: never render full PAN).

    '4111111111111234' -> '**** **** **** 1234'. Non-16-digit input -> last-4 form.
    """
    digits = _digits(str(card_no) if card_no is not None else "")
    if not digits:
        return ""
    if len(digits) <= 4:
        return CARD_MASK_CHAR * len(digits)
    last4 = digits[-4:]
    if len(digits) == 16:
        return f"{CARD_MASK_CHAR * 4} {CARD_MASK_CHAR * 4} {CARD_MASK_CHAR * 4} {last4}"
    return CARD_MASK_CHAR * (len(digits) - 4) + last4


def mask_phone(phone: str | None) -> str:
    """Mask a phone number, keeping the last 4 digits.

    '919900001234' -> '********1234'. Short/empty -> fully masked or ''.
    """
    digits = _digits(str(phone) if phone is not None else "")
    if not digits:
        return ""
    if len(digits) <= 4:
        return PHONE_MASK_CHAR * len(digits)
    return PHONE_MASK_CHAR * (len(digits) - 4) + digits[-4:]


def mask_email(email: str | None) -> str:
    """Mask the local part of an email, keeping the domain and first/last local char.

    'asha.mehta@example.com' -> 'a********a@example.com'. Non-emails -> generic mask.
    """
    s = (str(email) if email is not None else "").strip()
    if not s or "@" not in s:
        return "*" * len(s) if s else ""
    local, _, domain = s.partition("@")
    if not local:
        return f"@{domain}"
    if len(local) == 1:
        return f"{local}@{domain}"
    if len(local) == 2:
        return f"{local[0]}*@{domain}"
    return f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}@{domain}"


def mask_pan(pan: str | None) -> str:
    """Mask an Indian PAN, keeping the 4 sequence digits and final check char.

    'ABCDE1234F' -> 'XXXXX1234X'. Non-10-char input -> fully masked.
    """
    s = (str(pan) if pan is not None else "").strip().upper()
    if not s:
        return ""
    if len(s) != 10:
        return ACCOUNT_MASK_CHAR * len(s)
    # PAN format AAAAA9999A: mask the 5 letters and the final check letter.
    return f"{ACCOUNT_MASK_CHAR * 5}{s[5:9]}{ACCOUNT_MASK_CHAR}"


# High-confidence inline patterns for free-text sweeping. Conservative on purpose:
# only matches sequences unlikely to be legitimate IDs we want to keep visible.
_CARD_RE = re.compile(r"\b(?:\d[ -]?){15,16}\d\b")
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")


def mask_text(text: str | None) -> str:
    """Best-effort sweep over free text, masking embedded card numbers and PANs.

    Use for narration / counterparty fields where a number may appear inline.
    Deliberately conservative: it does NOT touch loan/claim/policy IDs or amounts.
    """
    s = str(text) if text is not None else ""
    if not s:
        return ""
    s = _CARD_RE.sub(lambda m: mask_card(m.group(0)), s)
    s = _PAN_RE.sub(lambda m: mask_pan(m.group(0)), s)
    return s
