from shared.utils.in_memory_store import store


def get_profile(customer_id: str):
    conversation_id = store.customer_to_conversation.get(customer_id)
    if not conversation_id:
        return None
    return store.conversations[conversation_id].profile
