from services.analytics_service.metrics import get_metrics


def snapshot() -> dict[str, int]:
    return get_metrics()
