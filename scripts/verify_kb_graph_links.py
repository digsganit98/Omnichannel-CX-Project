"""Verify Phase 2 - that KB chunks are actually connected to the customer graph.

Phase 1 only co-locates KB chunks with the customer records. This checks the
part that makes them one graph: (:KBChunk)-[:ABOUT]->(:Product), and whether a
real customer can be walked from their own holdings to the KB text about them.

Makes no LLM calls. Run after /admin/rag/index and /admin/rag/link-kb-graph:

    docker compose exec api python scripts/verify_kb_graph_links.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Recorded in kb_graph_links.py: no product in the catalogue sells these.
EXPECTED_UNLINKED = 3


def main() -> int:
    os.environ.setdefault("RAG_BACKEND", "neo4j")
    from services.neo4j_service.client import Neo4jClient

    client = Neo4jClient()
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str) -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")
        if not ok:
            failures.append(label)

    try:
        print("\n== 1. chunks and links exist ==")
        chunks = client.query("MATCH (k:KBChunk) RETURN count(k) AS n")[0]["n"]
        check("chunks indexed", chunks > 0, f"{chunks} (:KBChunk) nodes")

        links = client.query(
            "MATCH (:KBChunk)-[r:ABOUT]->(:Product) RETURN count(r) AS n"
        )[0]["n"]
        check("ABOUT edges", links > 0, f"{links} chunk->product edges")

        linked = client.query(
            "MATCH (k:KBChunk) WHERE (k)-[:ABOUT]->() OR (k)-[:ABOUT_TOPIC]->() "
            "RETURN count(DISTINCT k) AS n"
        )[0]["n"]
        unlinked = chunks - linked
        check(
            "unlinked count as documented",
            unlinked == EXPECTED_UNLINKED,
            f"{unlinked} unlinked (expected {EXPECTED_UNLINKED}: demat, sip, elss)",
        )

        print("\n== 2. no chunk links to a product that does not exist ==")
        orphans = client.query(
            "MATCH (k:KBChunk)-[:ABOUT]->(p) WHERE NOT p:Product RETURN count(*) AS n"
        )[0]["n"]
        check("no dangling ABOUT targets", orphans == 0, f"{orphans} non-Product targets")

        print("\n== 3. the traversal that justifies Phase 2 ==")
        rows = client.query(
            """
            MATCH (c:Customer)-[]->(h)-[:PRODUCT_IS]->(p:Product)<-[:ABOUT]-(k:KBChunk)
            RETURN DISTINCT c.name AS customer, k.topic AS topic, p.name AS product
            ORDER BY customer, topic
            """
        )
        check("customers reach KB via holdings", len(rows) > 0,
              f"{len(rows)} customer->holding->product->chunk paths")
        for row in rows[:10]:
            print(f"        {row['customer']:20s} {row['topic']:26s} <- {row['product']}")
        if len(rows) > 10:
            print(f"        ... {len(rows) - 10} more")

        print("\n== 4. every customer reaches at least one chunk ==")
        rows = client.query(
            """
            MATCH (c:Customer)
            OPTIONAL MATCH (c)-[]->(h)-[:PRODUCT_IS]->(:Product)<-[:ABOUT]-(k:KBChunk)
            RETURN c.name AS customer, count(DISTINCT k) AS chunks
            ORDER BY chunks
            """
        )
        for row in rows:
            print(f"        {row['customer']:22s} {row['chunks']} chunks")
        starved = [r["customer"] for r in rows if r["chunks"] == 0]
        check(
            "no customer is cut off from the KB",
            not starved,
            "all customers reachable" if not starved else f"unreachable: {starved}",
        )

        print("\n== 5. graph filter re-ranks without dropping results ==")
        from services.rag_service.neo4j_store import Neo4jVectorStore

        store = Neo4jVectorStore(client)
        # Pick the customer BY the topic being probed. Picking any customer with
        # links and then asking a fixed question tests nothing: the first such
        # customer may hold no card, so a card question tags nothing and the
        # check fails for a reason that is not a defect.
        probe_topic = "card_loss_reporting"
        query = "I lost my card, what should I do?"
        cid_rows = client.query(
            """
            MATCH (c:Customer)-[]->()-[:PRODUCT_IS]->(:Product)<-[:ABOUT]-(k:KBChunk)
            WHERE k.topic = $topic
            RETURN c.customer_id AS id, c.name AS name LIMIT 1
            """,
            {"topic": probe_topic},
        )
        if not cid_rows:
            check("filter probe", False,
                  f"no customer holds a product linked to '{probe_topic}'")
        else:
            cid = cid_rows[0]["id"]
            print(f"        probing as {cid_rows[0]['name']} ({cid}), who holds a "
                  f"product linked to '{probe_topic}'")
            os.environ["KB_GRAPH_FILTER"] = "false"
            plain = store.similarity_search(query, k=4)
            os.environ["KB_GRAPH_FILTER"] = "true"
            filtered = store.similarity_search(query, k=4, customer_id=cid)
            check(
                "filter returns the same number of results",
                len(filtered) == len(plain),
                f"{len(plain)} unfiltered vs {len(filtered)} filtered "
                "(a re-rank must not drop results)",
            )
            tagged = sum(
                1 for h in filtered if h["metadata"].get("customer_product_match")
            )
            check("holdings are tagged", tagged > 0,
                  f"{tagged}/{len(filtered)} tagged as products this customer holds")
    finally:
        client.close()

    print("\n" + "=" * 62)
    if failures:
        print(f"FAILED: {len(failures)} check(s): {', '.join(failures)}")
        return 1
    print("All Phase 2 checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
