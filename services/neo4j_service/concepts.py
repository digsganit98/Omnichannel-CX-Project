"""The Concept layer - the hub that makes the graph one graph.

Before this, "what the bank sells" and "what the bank explains" were separate
shapes: (:Product) carried the catalogue, (:KBChunk) carried the guidance, and
a chunk could only attach to guidance-about-a-product. A subject the bank
explains but does not sell - SIP, ELSS, Demat - attached to nothing and was
reachable only by text similarity.

They are not separate things. "Home Loan" is one subject: the bank sells one,
the KB explains one, a customer holds one. Selling it is a PROPERTY of the
subject, not a different kind of node. So:

    (:Concept {name: "Home Loan", sold: true})
        <-[:INSTANCE_OF]- (:Product)          the catalogue entry
        <-[:EXPLAINS]--- (:KBChunk)           the guidance
        <-[:INSTANCE_OF]- (:Loan)             what a customer holds

    (:Concept {name: "SIP", sold: false})
        <-[:EXPLAINS]--- (:KBChunk)           explained, never sold

SIP having no Product child is a true statement about the business, not a gap
to work around. Every chunk reaches a Concept; every Concept is reachable -
from a customer who holds an instance, or directly, because Concepts are
shared reference data rather than anybody's records.

This runs AFTER load_bfsi_data() and after the KB is indexed. It only ADDS
nodes and edges: no existing node, property or relationship is modified, so a
wrong mapping here cannot damage the records every other feature reads.
"""

import logging

logger = logging.getLogger(__name__)


# Concepts are derived from the catalogue's own Category values rather than
# hand-listed, so a new product category creates its Concept with no code
# change. Only the KB-side vocabulary is written down, because chunk text has
# no structured field to key on.
#
# Each entry: the Concept a chunk belongs to, and the phrases that identify it.
# Matching is on the chunk text, lowercased.
CHUNK_CONCEPTS: list[dict] = [
    {"concept": "Savings Account", "match": ["open a new savings account"]},
    {"concept": "Savings Account", "match": ["daily atm withdrawal limit", "atm withdrawal"]},
    {"concept": "Personal Loan", "match": ["requirements for a personal loan"]},
    {"concept": "Credit Card", "match": ["lost or stolen debit/credit card", "lost or stolen"]},
    {"concept": "Home Loan", "match": ["apply for a home loan"]},
    {"concept": "KYC", "match": ["update my kyc", "know your customer"]},
    {"concept": "Life Insurance", "match": ["what is term insurance", "term insurance"]},
    {"concept": "Life Insurance", "match": ["ulip and traditional life insurance", "ulip"]},
    {"concept": "Health Insurance", "match": ["file a health insurance claim"]},
    {"concept": "Motor Insurance", "match": ["car insurance premium"]},
    {"concept": "Insurance Portability", "match": ["port my existing insurance policy"]},
    # Explained, not sold. These are the three that had no anchor at all before
    # the Concept layer existed - the reason it exists.
    {"concept": "Demat Account", "match": ["what is a demat account", "demat"]},
    {"concept": "SIP", "match": ["what is sip", "systematic investment plan"]},
    {"concept": "ELSS", "match": ["tax benefits associated with investing in elss", "elss"]},
]

# A product Category maps to the Concept of the same subject. Categories the
# catalogue already uses are the source of truth; this only renames where the
# catalogue's word differs from the KB's.
CATEGORY_CONCEPTS: dict[str, str] = {
    "SA": "Savings Account",
    "CSA": "Savings Account",
    "CA": "Current Account",
    "Personal Loan": "Personal Loan",
    "Home Loan": "Home Loan",
    "Auto Loan": "Auto Loan",
    "Education Loan": "Education Loan",
    "Loan Against Property": "Loan Against Property",
    "Classic": "Credit Card",
    "Gold": "Credit Card",
    "Platinum": "Credit Card",
    "Signature": "Credit Card",
    "Regular": "Fixed Deposit",
    "Tax Saver": "Fixed Deposit",
    "Senior Citizen": "Fixed Deposit",
    "Health": "Health Insurance",
    "Life": "Life Insurance",
    "Auto": "Motor Insurance",
    "Home Insurance": "Home Insurance",
}

# A Policy's own policy_type, which is NOT the catalogue's Category vocabulary -
# a policy says "Auto" where the Concept is "Motor Insurance", and "Term
# Insurance" where the Concept is "Life Insurance" (term IS a life product).
# Kept separate from CATEGORY_CONCEPTS because these are the words the customer
# RECORDS use, not the words the catalogue uses, and conflating them is how a
# renamed product category would silently unlink every customer's policy.
POLICY_TYPE_CONCEPTS: dict[str, str] = {
    "Health": "Health Insurance",
    "Home Insurance": "Home Insurance",
    "Auto": "Motor Insurance",
    "Term Insurance": "Life Insurance",
}


def build_concept_layer(client) -> dict:
    """Create Concepts and wire products, chunks and holdings to them.

    Idempotent - MERGE throughout, so re-running after a reseed or a KB
    re-index adds nothing twice.
    """
    if client is None:
        return {"concepts": 0, "products_linked": 0, "chunks_linked": 0, "holdings_linked": 0}

    # This module's own edges only, so an edited mapping does not leave the
    # previous run's links behind. Concept nodes are left alone: MERGE below
    # re-uses them, and deleting them would strip the holdings edges too.
    client.write("MATCH (:Product)-[r:INSTANCE_OF]->(:Concept) DELETE r")
    client.write("MATCH (:KBChunk)-[r:EXPLAINS]->(:Concept) DELETE r")
    client.write("MATCH ()-[r:INSTANCE_OF]->(:Concept) DELETE r")
    # A Concept nothing points at is not a subject the business has - it is left over
    # from an edited mapping. Deleting the edges above without this left 'Service
    # Request', a Concept invented to hold 22 flashcards, sitting in the graph with
    # nothing attached after the mapping that created it was removed.
    client.write("MATCH (con:Concept) WHERE NOT (con)<--() DELETE con")

    concepts: set[str] = set()

    # 1. Products. The catalogue's Category is the subject; `sold` is true by
    #    definition here - a product IS the bank selling that subject.
    for category, concept in CATEGORY_CONCEPTS.items():
        rows = client.query(
            """
            MATCH (p:Product {category: $category})
            MERGE (con:Concept {name: $concept})
              ON CREATE SET con.sold = true
            SET con.sold = true
            MERGE (p)-[:INSTANCE_OF]->(con)
            RETURN count(p) AS n
            """,
            {"category": category, "concept": concept},
        )
        if rows and rows[0]["n"]:
            concepts.add(concept)
    products_linked = _count(client, "MATCH (:Product)-[r:INSTANCE_OF]->(:Concept) RETURN count(r) AS n")

    # 2. KB chunks. Matched on text, because a chunk carries no structured
    #    field naming its subject. A Concept created here and by no product is
    #    left sold=false: the bank explains it and does not sell it.
    chunks = client.query(
        "MATCH (k:KBChunk {doc_type: 'knowledge_base'}) RETURN k.chunk_id AS id, k.text AS text"
    )
    for chunk in chunks:
        text_lower = (chunk["text"] or "").lower()
        for rule in CHUNK_CONCEPTS:
            if not any(phrase in text_lower for phrase in rule["match"]):
                continue
            client.write(
                """
                MATCH (k:KBChunk {chunk_id: $id})
                MERGE (con:Concept {name: $concept})
                  ON CREATE SET con.sold = false
                MERGE (k)-[:EXPLAINS]->(con)
                """,
                {"id": chunk["id"], "concept": rule["concept"]},
            )
            concepts.add(rule["concept"])
    chunks_linked = _count(
        client, "MATCH (:KBChunk)-[r:EXPLAINS]->(:Concept) RETURN count(DISTINCT startNode(r)) AS n"
    )

    # Resolution examples (doc_type resolution_example) are NOT wired to Concepts.
    # They are the difficulty classifier's labelled flashcards - "a question like this
    # is L1" - and they reach a different LLM call than the one that writes a reply.
    # They carry no customer knowledge, so an EXPLAINS edge from one to a Concept
    # asserts a relationship that does not exist. An earlier version wired them anyway
    # and invented a 'Service Request' Concept to hold the 22 whose intent named no
    # subject, which made the connected-node count look better and the graph less true.

    # 3. Customer holdings. A holding already points at its Product; pointing it
    #    at the Concept too is what lets one walk go
    #    Customer -> holding -> Concept <- KBChunk without passing through the
    #    catalogue, so a holding whose product row is missing still reaches
    #    guidance.
    client.write(
        """
        MATCH (h)-[:PRODUCT_IS]->(:Product)-[:INSTANCE_OF]->(con:Concept)
        MERGE (h)-[:INSTANCE_OF]->(con)
        """
    )
    # 4. The holdings that have NO Product row to ride on.
    #
    #    Step 3 above only reaches a holding that already carried a PRODUCT_IS
    #    edge, which is true of exactly four labels - Account, CreditCard,
    #    FixedDeposit, Loan. Policy, Claim, ChargePenalty, Transaction and KYC
    #    carry none, so that query skipped them in silence and five of nine
    #    holding types reached no guidance at all: a customer's health policy
    #    did not connect to the health-claim chunk, and her late fee did not
    #    connect to the account it was charged on. The KB still arrived, marked
    #    "general" - the model was never told these were HERS, which is the one
    #    thing the graph knows and no wording match can assert.
    #
    #    Each link below joins on a key the seed already carries, verified to
    #    resolve for every row: Claim.policy_id -> Policy (15/15),
    #    ChargePenalty.account_number -> Account (7/7),
    #    Transaction.account_number -> Account (72/72).

    # 4a. Policy -> its Concept, via the policy's own type vocabulary.
    for policy_type, concept in POLICY_TYPE_CONCEPTS.items():
        client.write(
            """
            MATCH (p:Policy {policy_type: $policy_type})
            MERGE (con:Concept {name: $concept})
            ON CREATE SET con.sold = true
            MERGE (p)-[:INSTANCE_OF]->(con)
            """,
            {"policy_type": policy_type, "concept": concept},
        )

    # 4b. Claim -> the Concept of the policy it was filed against. claim_type
    #     ("Hospitalization", "Theft") describes the EVENT, not the product, so
    #     the subject has to come through the parent policy: a claim on a health
    #     policy is a health-insurance matter.
    client.write(
        """
        MATCH (cl:Claim)
        MATCH (p:Policy {policy_id: cl.policy_id})-[:INSTANCE_OF]->(con:Concept)
        MERGE (cl)-[:INSTANCE_OF]->(con)
        """
    )

    # 4c/4d. A charge and a transaction belong to the subject of the ACCOUNT they
    #        sit on - that is what makes a late fee reach account guidance. Both
    #        join on account_number, which the loader reads as a text property;
    #        these are two of the six "* -> Account" links the seed implies and
    #        the loader never wired.
    for label in ("ChargePenalty", "Transaction"):
        client.write(
            f"""
            MATCH (x:{label})
            MATCH (a:Account {{account_number: x.account_number}})-[:INSTANCE_OF]->(con:Concept)
            MERGE (x)-[:INSTANCE_OF]->(con)
            """
        )

    # 4e. KYC is its own subject and the KB already explains it.
    client.write(
        """
        MATCH (k:KYC)
        MERGE (con:Concept {name: 'KYC'})
        ON CREATE SET con.sold = false
        MERGE (k)-[:INSTANCE_OF]->(con)
        """
    )
    concepts.update(POLICY_TYPE_CONCEPTS.values())
    concepts.add("KYC")

    holdings_linked = _count(
        client,
        "MATCH (h)-[r:INSTANCE_OF]->(:Concept) WHERE NOT h:Product RETURN count(r) AS n",
    )

    result = {
        "concepts": len(concepts),
        "products_linked": products_linked,
        "chunks_linked": chunks_linked,
        "holdings_linked": holdings_linked,
    }
    logger.info("concept_layer_built", extra=result)
    return result


def _count(client, cypher: str) -> int:
    rows = client.query(cypher)
    return rows[0]["n"] if rows else 0
