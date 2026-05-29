from shared.utils.in_memory_store import store


def get_metrics() -> dict[str, int]:
    return dict(store.metrics)
