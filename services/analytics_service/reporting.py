from services.analytics_service.metrics import get_metrics


def build_report() -> str:
    metrics = get_metrics()
    return "\n".join(f"{name}: {value}" for name, value in metrics.items())
