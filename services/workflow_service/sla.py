def sla_hours(priority: str) -> int:
    return {"high": 4, "medium": 12, "low": 24}.get(priority, 24)
