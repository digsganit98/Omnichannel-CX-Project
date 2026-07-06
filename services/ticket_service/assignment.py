from shared.constants.intents import INTENT_TO_TEAM


def assign_team(intent: str) -> str:
    return INTENT_TO_TEAM.get(intent, "customer_support")
