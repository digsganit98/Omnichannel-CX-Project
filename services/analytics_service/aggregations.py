from shared.utils.in_memory_store import store


def channel_mix() -> dict[str, int]:
    return {
        "email": store.metrics.get("email_messages", 0),
        "whatsapp": store.metrics.get("whatsapp_messages", 0),
    }
