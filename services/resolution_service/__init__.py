def resolve_query_level(query: str, intent: str, sentiment: str) -> dict:
    from services.resolution_service.classifier import resolve_query_level as _resolve_query_level

    return _resolve_query_level(query, intent, sentiment)


def __getattr__(name: str):
    if name == "ResolutionDecisionEngine":
        from services.resolution_service.classifier import ResolutionDecisionEngine

        return ResolutionDecisionEngine
    raise AttributeError(name)


__all__ = ["ResolutionDecisionEngine", "resolve_query_level"]
