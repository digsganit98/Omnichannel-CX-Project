"""Phase 2 - link KB chunks to the (:Product) nodes they describe.

Phase 1 puts KB chunks in Neo4j. On its own that only co-locates them: the
chunks sit beside the customer graph as islands, and retrieval is still pure
vector similarity. This module creates the edges that make them part of the
graph:

    (:KBChunk)-[:ABOUT]->(:Product)

With those in place, a customer holding PROD0002 (Dream Home Loan) can be
walked from their own (:Loan) to the KB chunk explaining how home loans are
applied for - retrieval anchored to what they actually hold, which text
similarity alone cannot express.

Matching is by product CATEGORY and TYPE, not by product id, so a chunk about
home loans links to every home-loan product in the catalogue and keeps working
when the catalogue changes. The rules are hand-written because the KB is 14
chunks; an extraction model here would add a dependency and a failure mode to
save a table that fits on one screen.

THREE CHUNKS INTENTIONALLY LINK TO NOTHING - Demat accounts, SIP and ELSS
describe investment products this bank's catalogue does not carry. They stay
retrievable by vector search and unlinked in the graph. Inventing a
(:Product) for them would put products in the graph that the business does
not sell.
"""

import logging

logger = logging.getLogger(__name__)


# Each rule matches chunk text, then selects products by their catalogue fields.
# `match_any`: lowercase substrings; a chunk matching ANY of them gets the link.
# `product_types` / `categories`: matched against (:Product).product_type and
# .category from Products_Catalog. Empty list means "do not constrain on this".
LINK_RULES: list[dict] = [
    {
        "topic": "savings_account_opening",
        "match_any": ["open a new savings account", "open a new savings"],
        "product_types": ["SavingsAccount"],
        "categories": [],
    },
    {
        "topic": "personal_loan_eligibility",
        "match_any": ["requirements for a personal loan", "personal loan"],
        "product_types": ["Loan"],
        "categories": ["Personal Loan"],
    },
    {
        "topic": "card_loss_reporting",
        "match_any": ["lost or stolen debit/credit card", "lost or stolen"],
        "product_types": ["CreditCard"],
        "categories": [],
    },
    {
        "topic": "atm_withdrawal_limit",
        "match_any": ["daily atm withdrawal limit", "atm withdrawal"],
        "product_types": ["SavingsAccount", "CurrentAccount"],
        "categories": [],
    },
    {
        "topic": "home_loan_application",
        "match_any": ["apply for a home loan", "home loan"],
        "product_types": ["Loan"],
        "categories": ["Home Loan"],
    },
    {
        "topic": "term_insurance",
        "match_any": ["what is term insurance", "term insurance"],
        "product_types": ["Policy"],
        "categories": ["Life"],
    },
    {
        "topic": "health_claim_filing",
        "match_any": ["file a health insurance claim", "health insurance claim"],
        "product_types": ["Policy"],
        "categories": ["Health"],
    },
    {
        "topic": "motor_premium_factors",
        "match_any": ["car insurance premium", "motor insurance premium"],
        "product_types": ["Policy"],
        "categories": ["Auto"],
    },
    {
        "topic": "policy_portability",
        "match_any": ["port my existing insurance policy", "port my existing"],
        "product_types": ["Policy"],
        "categories": [],
    },
    {
        "topic": "ulip_vs_traditional",
        "match_any": ["ulip and traditional life insurance", "ulip"],
        "product_types": ["Policy"],
        "categories": ["Life"],
    },
]

# KYC is not a product - it links to the per-customer (:KYC) node instead, so a
# KYC question can reach both the customer's own verification status and the
# procedure for updating it.
KYC_RULE = {
    "topic": "kyc_update",
    "match_any": ["update my kyc", "know your customer"],
}

# Recorded so the count is auditable rather than a silent gap.
UNLINKED_TOPICS = ["demat_account", "sip_investment", "elss_tax_benefit"]


def _matches(text_lower: str, needles: list[str]) -> bool:
    return any(needle in text_lower for needle in needles)


def link_kb_chunks_to_graph(client) -> dict:
    """Create (:KBChunk)-[:ABOUT]->(:Product) and -[:ABOUT_TOPIC]->(:KYC) edges.

    Idempotent: MERGE on both the nodes and the relationships, so re-running
    after a re-index adds nothing twice. Must run AFTER index_documents(),
    which is what creates the (:KBChunk) nodes.
    """
    chunks = client.query(
        "MATCH (k:KBChunk {doc_type: 'knowledge_base'}) "
        "RETURN k.chunk_id AS chunk_id, k.text AS text"
    )
    if not chunks:
        return {"chunks": 0, "links": 0, "linked_chunks": 0, "unlinked_chunks": 0}

    # Clear only this module's own edges, so a re-run after an edited rule does
    # not leave the previous rule's links behind.
    client.write("MATCH (:KBChunk)-[r:ABOUT]->() DELETE r")
    client.write("MATCH (:KBChunk)-[r:ABOUT_TOPIC]->() DELETE r")

    links = 0
    linked_chunk_ids: set[str] = set()

    for chunk in chunks:
        text_lower = (chunk["text"] or "").lower()
        chunk_id = chunk["chunk_id"]

        for rule in LINK_RULES:
            if not _matches(text_lower, rule["match_any"]):
                continue
            rows = client.query(
                """
                MATCH (k:KBChunk {chunk_id: $chunk_id})
                MATCH (p:Product)
                WHERE ($product_types = [] OR p.product_type IN $product_types)
                  AND ($categories = [] OR p.category IN $categories)
                MERGE (k)-[r:ABOUT]->(p)
                SET k.topic = $topic
                RETURN count(r) AS created
                """,
                {
                    "chunk_id": chunk_id,
                    "product_types": rule["product_types"],
                    "categories": rule["categories"],
                    "topic": rule["topic"],
                },
            )
            created = rows[0]["created"] if rows else 0
            if created:
                links += created
                linked_chunk_ids.add(chunk_id)

        if _matches(text_lower, KYC_RULE["match_any"]):
            rows = client.query(
                """
                MATCH (k:KBChunk {chunk_id: $chunk_id})
                MATCH (y:KYC)
                MERGE (k)-[r:ABOUT_TOPIC]->(y)
                SET k.topic = $topic
                RETURN count(r) AS created
                """,
                {"chunk_id": chunk_id, "topic": KYC_RULE["topic"]},
            )
            created = rows[0]["created"] if rows else 0
            if created:
                links += created
                linked_chunk_ids.add(chunk_id)

    result = {
        "chunks": len(chunks),
        "links": links,
        "linked_chunks": len(linked_chunk_ids),
        "unlinked_chunks": len(chunks) - len(linked_chunk_ids),
        "expected_unlinked_topics": UNLINKED_TOPICS,
    }
    logger.info("kb_graph_links_built", extra=result)
    return result
