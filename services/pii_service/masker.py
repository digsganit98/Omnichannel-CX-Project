"""Deterministic PII masking for text sent to third-party LLMs (Groq).

Not NER — BFSI PII (PAN, Aadhar, Indian mobile numbers, email, card numbers) is highly
structured and regex-detectable with near-100% precision, so no ML/NER dependency is
needed. Mirrors the deterministic safety-net pattern already used in
services/resolution_service/classifier.py (HIGH_RISK_PATTERNS / _high_risk_match).

Scope: identity-linking PII only (name, phone, email, PAN, Aadhar, real bank-issued card
numbers). Internal reference IDs (LoanID, ClaimID, PolicyID, our own CardID/AccountNumber
formats) and monetary amounts are deliberately NOT masked — the LLM needs them to generate
a useful answer, and they aren't classic identifying PII on their own.
"""

import re

from services.pii_service.config import pii_masking_enabled

_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAR_MASKED_RE = re.compile(r"\bX{4}[\s-]X{4}[\s-]\d{4}\b", re.IGNORECASE)
# Grouped format only here (unambiguous). Plain ungrouped 12-digit Aadhar is handled by
# _AADHAR_PLAIN_RE, run AFTER phone — otherwise "+91<10-digit-phone>" (12 digits once the
# "+" is stripped) gets misdetected as an Aadhar number before the phone pattern runs.
_AADHAR_GROUPED_RE = re.compile(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}\b")
_AADHAR_PLAIN_RE = re.compile(r"\b\d{12}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Real bank-issued card numbers only (Luhn-validated below) — deliberately broad candidate
# regex here, narrowed by the Luhn check so it doesn't collide with this app's internal
# 14-digit account numbers or loan amounts, which aren't Luhn-valid.
_CARD_CANDIDATE_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn_valid(digits: str) -> bool:
    if not digits.isdigit() or not (13 <= len(digits) <= 19):
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


class PIIMasker:
    """Masks identity-linking PII before text is sent to an external LLM, and restores
    it in the LLM's response before that response is shown to the customer.

    The placeholder mapping is ephemeral and per-call only — build it right before one
    LLM round-trip and discard it after. No persistent vault: this app only ever needs
    same-request restore, never cross-session reversibility.
    """

    def mask(self, text: str, known_values: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
        if not text or not pii_masking_enabled():
            return text, {}

        mapping: dict[str, str] = {}
        counters: dict[str, int] = {}
        masked = text

        def next_placeholder(label: str) -> str:
            counters[label] = counters.get(label, 0) + 1
            return f"[{label}_{counters[label]}]"

        # 1. Known values first (the resolved customer's own name/phone/email from
        #    Neo4j) so they collapse to one stable placeholder each, rather than being
        #    re-detected piecemeal by the generic patterns below.
        if known_values:
            for label, value in (
                ("NAME", known_values.get("name")),
                ("PHONE", known_values.get("phone")),
                ("EMAIL", known_values.get("email")),
            ):
                if not value:
                    continue
                pattern = re.compile(re.escape(str(value)), re.IGNORECASE)
                if pattern.search(masked):
                    placeholder = next_placeholder(label)
                    mapping[placeholder] = str(value)
                    masked = pattern.sub(placeholder, masked)

        # 2. Structured regex patterns catch anything typed inline or not already known
        #    (e.g. a customer pasting their PAN, or Neo4j being unreachable).
        def sub_pattern(pattern: re.Pattern, label: str, validator=None) -> None:
            nonlocal masked

            def replace(match: re.Match) -> str:
                value = match.group(0)
                if validator and not validator(re.sub(r"[ -]", "", value)):
                    return value
                placeholder = next_placeholder(label)
                mapping[placeholder] = value
                return placeholder

            masked = pattern.sub(replace, masked)

        sub_pattern(_EMAIL_RE, "EMAIL")
        sub_pattern(_PAN_RE, "PAN")
        sub_pattern(_AADHAR_MASKED_RE, "AADHAR")
        sub_pattern(_AADHAR_GROUPED_RE, "AADHAR")
        sub_pattern(_PHONE_RE, "PHONE")
        sub_pattern(_AADHAR_PLAIN_RE, "AADHAR")
        sub_pattern(_CARD_CANDIDATE_RE, "CARD", validator=_luhn_valid)

        return masked, mapping

    def unmask(self, text: str, mapping: dict[str, str]) -> str:
        if not text or not mapping:
            return text
        restored = text
        for placeholder, original in mapping.items():
            restored = restored.replace(placeholder, original)
        return restored


_default_masker = PIIMasker()


def mask_text(text: str, known_values: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    return _default_masker.mask(text, known_values)


def unmask_text(text: str, mapping: dict[str, str]) -> str:
    return _default_masker.unmask(text, mapping)
