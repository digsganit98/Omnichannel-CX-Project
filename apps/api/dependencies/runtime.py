import os
from functools import lru_cache

from services.orchestration_service.graph import OrchestrationGraph
from services.orchestration_service.router import OmnichannelRouter
from services.persistence_service.repository import SQLiteCXRepository


@lru_cache
def get_repository() -> SQLiteCXRepository:
    return SQLiteCXRepository(os.getenv("DATABASE_PATH", "data/cx_phase1.db"))


@lru_cache
def get_router() -> OmnichannelRouter:
    return OmnichannelRouter(OrchestrationGraph(get_repository()))


def reset_runtime() -> None:
    get_router.cache_clear()
    get_repository.cache_clear()
