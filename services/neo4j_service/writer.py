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


def write_incoming_interaction(
    client,
    conversation_id: str,
    customer_id: str,
    channel: str,
    message_text: str,
    timestamp: str,
) -> None:
    """Write an :Interaction node in 'open' status the moment a message arrives.

    Called BEFORE the AI pipeline runs so the graph always has a record of every
    inbound message even if the pipeline fails partway through.
    """
    if client is None or not conversation_id or not customer_id:
        return
    try:
        client.write(
            """
            MERGE (i:Interaction {conversation_id: $conversation_id})
            SET i.channel    = $channel,
                i.message    = $message,
                i.status     = 'open',
                i.created_at = $timestamp
            WITH i
            MATCH (c:Customer {customer_id: $customer_id})
            MERGE (c)-[:HAS_INTERACTION]->(i)
            """,
            {
                "conversation_id": conversation_id,
                "customer_id": customer_id,
                "channel": channel or "",
                "message": message_text or "",
                "timestamp": timestamp or "",
            },
        )
    except Exception:
        logger.warning(
            "neo4j_write_incoming_interaction_failed",
            extra={"conversation_id": conversation_id},
            exc_info=True,
        )


def update_interaction_resolution(
    client,
    conversation_id: str,
    customer_id: str,
    resolution: str,
    intent: str,
    sentiment: str,
    product_id: str,
    embedding_str: str,
    urgency: str,
) -> None:
    """Update the :Interaction node with the AI resolution and create/update ResolutionMemory.

    Called AFTER the AI pipeline completes. Closes the open interaction and stores
    the answer as a reusable ResolutionMemory node keyed by (product_id, intent_type).
    """
    if client is None or not conversation_id:
        return
    try:
        from datetime import datetime, timezone
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        mem_id = "RESMEM-" + str(uuid.uuid4())[:8].upper()
        client.write(
            """
            MERGE (i:Interaction {conversation_id: $conversation_id})
            SET i.resolution           = $resolution,
                i.intent               = $intent,
                i.sentiment            = $sentiment,
                i.urgency              = $urgency,
                i.product_ref          = $product_id,
                i.resolution_embedding = $embedding,
                i.status               = 'closed',
                i.handled_by           = 'AI_GROQ',
                i.updated_at           = $now

            WITH i
            MERGE (rm:ResolutionMemory {product_id: $product_id, intent_type: $intent})
            ON CREATE SET
                rm.id                   = $mem_id,
                rm.query_pattern        = i.message,
                rm.resolution_text      = $resolution,
                rm.resolution_embedding = $embedding,
                rm.verified             = false,
                rm.times_reused         = 1,
                rm.created_at           = $now
            ON MATCH SET
                rm.resolution_text      = $resolution,
                rm.resolution_embedding = $embedding,
                rm.times_reused         = rm.times_reused + 1,
                rm.updated_at           = $now

            MERGE (i)-[:CREATED_MEMORY]->(rm)

            WITH i
            MATCH (a:Agent {agent_id: 'AI_GROQ'})
            MERGE (i)-[:HANDLED_BY]->(a)
            """,
            {
                "conversation_id": conversation_id,
                "resolution": resolution or "",
                "intent": intent or "",
                "sentiment": sentiment or "",
                "urgency": urgency or "",
                "product_id": product_id or "general",
                "embedding": embedding_str or "",
                "mem_id": mem_id,
                "now": now,
            },
        )
    except Exception:
        logger.warning(
            "neo4j_update_interaction_resolution_failed",
            extra={"conversation_id": conversation_id},
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
