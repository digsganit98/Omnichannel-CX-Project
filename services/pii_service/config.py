import os


def pii_masking_enabled() -> bool:
    return os.getenv("PII_MASKING_ENABLED", "true").lower() == "true"
