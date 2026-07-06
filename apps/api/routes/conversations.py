from fastapi import APIRouter, Depends, HTTPException

from apps.api.dependencies.runtime import get_repository
from apps.api.dependencies.security import require_admin_key

router = APIRouter(prefix="/admin/conversations", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str) -> dict:
    conversation = get_repository().get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("")
def list_conversations() -> list[dict]:
    return get_repository().list_conversations()
