from fastapi import APIRouter, Depends

from apps.api.dependencies.security import require_admin_key
from services.rag_service.config import embedding_backend, embedding_dimension, embedding_model
from services.rag_service.generator import OllamaGenerator
from services.orchestration_service.graph import ORCHESTRATION_ENGINE, WORKFLOW_EDGES
from services.orchestration_service.state import WorkflowStep

router = APIRouter(
    prefix="/admin/orchestration",
    tags=["admin"],
    dependencies=[Depends(require_admin_key)],
)


@router.get("/workflow")
def workflow_definition() -> dict:
    return {
        "engine": ORCHESTRATION_ENGINE,
        "framework": "LangGraph",
        "agents": [
            {
                "name": "intent_detection_agent",
                "responsibility": "Classify intent, urgency, sentiment, confidence, and reason.",
                "execution": "ollama_llm_with_validated_rule_fallback",
            },
            {
                "name": "query_resolution_agent",
                "responsibility": "Retrieve verified knowledge and generate cited customer answers.",
                "execution": "sentence_transformer_retrieval_and_ollama_llm_generation",
            },
            {
                "name": "ticket_management_agent",
                "responsibility": "Decide escalation, create durable tickets, and synchronize CRM records.",
                "execution": "deterministic_business_policy",
            },
            {
                "name": "workflow_automation_agent",
                "responsibility": "Load context, compose the final action, deliver replies, and persist results.",
                "execution": "deterministic_workflow_automation",
            },
        ],
        "steps": [step.value for step in WorkflowStep],
        "edges": [{"from": source, "to": destination} for source, destination in WORKFLOW_EDGES],
    }


@router.get("/ai-runtime")
def ai_runtime_status() -> dict:
    return {
        "llm": OllamaGenerator().status(check_connection=True),
        "embeddings": {
            "configured_backend": embedding_backend(),
            "model": embedding_model(),
            "dimension": embedding_dimension(),
            "verification": "Use GET /admin/rag/health to load the model and inspect active_backend.",
        },
    }
