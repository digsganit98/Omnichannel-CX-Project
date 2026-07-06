from services.retrieval_service.hybrid_search import SearchResult


def rerank(results: list[SearchResult]) -> list[SearchResult]:
    return sorted(results, key=lambda result: result.score, reverse=True)
