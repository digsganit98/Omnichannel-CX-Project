from fastapi import APIRouter, HTTPException

from shared.utils.in_memory_store import store

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    conversation = store.conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation.model_dump()


@router.get("")
def list_conversations() -> list[dict]:
    return [conversation.model_dump() for conversation in store.conversations.values()]
