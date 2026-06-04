from fastapi import APIRouter, Depends

from apps.api.dependencies.security import require_admin_key
from services.rag_service.config import embedding_backend, embedding_dimension, embedding_model
from services.rag_service.groq_generator import GroqGenerator
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
                "name": "intent_classification_agent",
                "responsibility": "Classify BFSI intent, urgency, sentiment with Groq LLM; enrich context from Neo4j customer graph.",
                "execution": "groq_llm_with_neo4j_enrichment_and_rule_fallback",
            },
            {
                "name": "query_resolution_agent",
                "responsibility": "Route to Neo4j (transactional intents) or RAG/KB (policy and general). Return cited answers.",
                "execution": "neo4j_graph_or_opensearch_rag_with_groq_generation",
            },
            {
                "name": "ticket_creation_agent",
                "responsibility": "Decide when human review is needed, create JIRA tickets, and synchronise CRM records.",
                "execution": "deterministic_bfsi_escalation_policy_with_jira_sync",
            },
        ],
        "steps": [step.value for step in WorkflowStep],
        "edges": [{"from": source, "to": destination} for source, destination in WORKFLOW_EDGES],
    }


@router.get("/ai-runtime")
def ai_runtime_status() -> dict:
    return {
        "llm": GroqGenerator().status(check_connection=True),
        "embeddings": {
            "configured_backend": embedding_backend(),
            "model": embedding_model(),
            "dimension": embedding_dimension(),
            "verification": "Use GET /admin/rag/health to load the model and inspect active_backend.",
        },
    }
