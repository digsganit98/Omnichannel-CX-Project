"""Real-time Neo4j writer for runtime customer interaction data.

All functions use MERGE so they are safe to call repeatedly with the same IDs —
existing nodes are updated, new nodes are created. Every function is a no-op when
``client`` is None so callers don't need to guard against a disabled graph.
"""

import logging

logger = logging.getLogger(__name__)


def upsert_customer(client, customer_id: str, phone: str, name: str, channel: str = "") -> None:
    """Create or update a :Customer node from a runtime inbound message.

    If the customer already exists (loaded from bfsi.xlsx), only the runtime
    fields (phone, display_name, channel) are SET — BFSI fields like loans/claims
    are untouched.
    """
    if client is None or not customer_id:
        return
    try:
        client.write(
            """
            MERGE (c:Customer {customer_id: $customer_id})
            SET c.phone        = CASE WHEN $phone <> '' THEN $phone ELSE c.phone END,
                c.display_name = CASE WHEN $name  <> '' THEN $name  ELSE c.display_name END,
                c.channel      = $channel
            """,
            {"customer_id": customer_id, "phone": phone or "", "name": name or "", "channel": channel},
        )
    except Exception:
        logger.warning("neo4j_upsert_customer_failed", extra={"customer_id": customer_id}, exc_info=True)


def upsert_interaction(
    client,
    customer_id: str,
    conversation_id: str,
    intent: str,
    urgency: str,
    channel: str,
    timestamp: str,
) -> None:
    """Create or update an :Interaction node and link it to the customer.

    Each conversation_id maps to exactly one Interaction node. Repeated calls
    (e.g., multiple turns in the same conversation) update the existing node.
    """
    if client is None or not customer_id or not conversation_id:
        return
    try:
        client.write(
            """
            MERGE (i:Interaction {conversation_id: $conversation_id})
            SET i.intent    = $intent,
                i.urgency   = $urgency,
                i.channel   = $channel,
                i.timestamp = $timestamp
            WITH i
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_INTERACTION]->(i)
            """,
            {
                "conversation_id": conversation_id,
                "customer_id": customer_id,
                "intent": intent or "",
                "urgency": urgency or "",
                "channel": channel or "",
                "timestamp": timestamp or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_upsert_interaction_failed",
            extra={"customer_id": customer_id, "conversation_id": conversation_id},
            exc_info=True,
        )


def upsert_ticket_node(
    client,
    ticket_id: str,
    customer_id: str,
    intent: str,
    priority: str,
    status: str,
) -> None:
    """Create or update a :Ticket node and link it to the customer."""
    if client is None or not ticket_id or not customer_id:
        return
    try:
        client.write(
            """
            MERGE (t:Ticket {ticket_id: $ticket_id})
            SET t.intent   = $intent,
                t.priority = $priority,
                t.status   = $status
            WITH t
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_TICKET]->(t)
            """,
            {
                "ticket_id": ticket_id,
                "customer_id": customer_id,
                "intent": intent or "",
                "priority": priority or "",
                "status": status or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_upsert_ticket_failed",
            extra={"ticket_id": ticket_id, "customer_id": customer_id},
            exc_info=True,
        )
