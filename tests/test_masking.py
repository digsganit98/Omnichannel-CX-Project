"""Tests for shared.utils.masking — PII output-layer redaction helpers."""

from shared.utils.masking import (
    mask_account,
    mask_card,
    mask_email,
    mask_pan,
    mask_phone,
    mask_text,
)


def test_mask_account_keeps_last_4():
    # 14-char input -> 10 mask chars + last 4 visible.
    assert mask_account("50100123456789") == "XXXXXXXXXX6789"
    assert mask_account("123456789") == "XXXXX6789"


def test_mask_account_short_and_empty():
    assert mask_account("123") == "XXX"
    assert mask_account("") == ""
    assert mask_account(None) == ""


def test_mask_card_16_digit_grouped():
    assert mask_card("4111111111111234") == "**** **** **** 1234"


def test_mask_card_strips_separators_and_handles_short():
    assert mask_card("4111-1111-1111-1234") == "**** **** **** 1234"
    assert mask_card("12") == "**"
    assert mask_card(None) == ""


def test_mask_phone_keeps_last_4():
    assert mask_phone("919900001234") == "********1234"
    assert mask_phone("") == ""


def test_mask_email_keeps_domain():
    assert mask_email("asha.mehta@example.com") == "a********a@example.com"
    assert mask_email("ab@x.com") == "a*@x.com"
    assert mask_email("a@x.com") == "a@x.com"


def test_mask_email_non_email_input():
    assert mask_email("notanemail") == "**********"
    assert mask_email(None) == ""


def test_mask_pan():
    assert mask_pan("ABCDE1234F") == "XXXXX1234X"
    assert mask_pan("abcde1234f") == "XXXXX1234X"
    assert mask_pan("bad") == "XXX"


def test_mask_text_redacts_inline_card_and_pan():
    out = mask_text("Charge on card 4111111111111234 ref PAN ABCDE1234F today")
    assert "4111111111111234" not in out
    assert "ABCDE1234F" not in out
    assert "1234" in out  # last 4 still shown


def test_mask_text_leaves_normal_ids_untouched():
    # Loan/claim IDs and amounts must remain visible — they are the answer.
    text = "Loan LN12345601 Status: Approved, Amount: Rs.500,000"
    assert mask_text(text) == text
