def sla_hours(priority: str) -> int:
    return {"critical": 1, "high": 4, "medium": 12, "low": 24}.get(priority, 24)
