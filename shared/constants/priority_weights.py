"""Tunable weights/thresholds for smart case prioritization scoring.

Kept separate from services/ticket_service/priority_scoring.py so the scoring
formula can be retuned without touching logic code.
"""

URGENCY_POINTS = {"high": 40, "medium": 20, "low": 5}

SENTIMENT_POINTS = {"negative": 20, "neutral": 5, "positive": 0}

# Segment values come from data/synthetic/generate_bfsi_data.py's income-bucket mapping.
CUSTOMER_VALUE_POINTS = {
    "HNI": 15,
    "Affluent": 10,
    "Mass Affluent": 5,
    "Mass": 0,
}

# Total score is bucketed into a priority tier via these ascending thresholds.
PRIORITY_THRESHOLDS = {
    "critical": 70,
    "high": 45,
    "medium": 20,
    # anything below "medium" falls to "low"
}
