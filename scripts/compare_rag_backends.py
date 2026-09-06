"""Compare KB retrieval between the OpenSearch and Neo4j vector stores.

Answers one question: does RAG_BACKEND=neo4j retrieve the SAME chunks as the
tuned OpenSearch path? Retrieval is the only thing that changes, so this calls
store.similarity_search() directly and NEVER pipeline.answer() - generation
would spend Groq tokens per probe and add no signal about retrieval.

Run INSIDE the api container. sentence-transformers must actually load; on a
host where it falls back to hashing embeddings the scores are meaningless and
the two backends are being compared on the wrong vectors. The script refuses
to run on the fallback unless --allow-fallback is passed.

    docker compose exec api python scripts/compare_rag_backends.py

Both stores are read independently, so nothing is switched or destroyed:
OpenSearch keeps its index either way. Pass --index to (re)build both first.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Each probe names the chunk that SHOULD come back, identified by a phrase
# unique to it. Derived from the 14 chunks in the KB PDF, plus the awkward
# cases: paraphrases that share no words with the source, and an investment
# question whose chunk is deliberately unlinked in Phase 2.
PROBES: list[dict] = [
    {"q": "How do I apply for a home loan?", "expect": "apply for a home loan"},
    {"q": "What paperwork is needed to buy a house on finance?", "expect": "apply for a home loan"},
    {"q": "How can I open a new savings account?", "expect": "open a new savings account"},
    {"q": "What are the requirements for a personal loan?", "expect": "requirements for a personal loan"},
    {"q": "I lost my credit card, what should I do?", "expect": "lost or stolen"},
    {"q": "My wallet was stolen with my bank card inside", "expect": "lost or stolen"},
    {"q": "What is the maximum daily ATM withdrawal limit?", "expect": "atm withdrawal limit"},
    {"q": "How can I update my KYC details?", "expect": "update my kyc"},
    {"q": "What documents do I need to refresh my identity proof?", "expect": "update my kyc"},
    {"q": "What is a Demat account?", "expect": "demat"},
    {"q": "What is SIP?", "expect": "sip"},
    {"q": "Tax benefits of ELSS?", "expect": "elss"},
    {"q": "What is term insurance and who should buy it?", "expect": "term insurance"},
    {"q": "How do I file a health insurance claim?", "expect": "health insurance claim"},
    {"q": "My hospital bill needs to be claimed, what is the process?", "expect": "health insurance claim"},
    {"q": "What factors affect my car insurance premium?", "expect": "car insurance premium"},
    {"q": "Can I port my existing insurance policy?", "expect": "port my existing insurance"},
    {"q": "Difference between ULIP and traditional life insurance?", "expect": "ulip"},
]

TOP_K = 4


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def hit_rank(hits: list[dict], expect: str) -> int | None:
    """1-based rank of the expected chunk, or None if absent from top-k."""
    for position, hit in enumerate(hits, start=1):
        if expect.lower() in norm(hit.get("text", "")).lower():
            return position
    return None


def build_store(backend: str):
    os.environ["RAG_BACKEND"] = backend
    # config reads os.environ at call time, but the store classes are imported
    # once - so import inside the function, after the env var is set.
    from services.rag_service.rag_pipeline import build_vector_store

    return build_vector_store()


def probe(store) -> list[dict]:
    rows = []
    for case in PROBES:
        try:
            hits = store.similarity_search(case["q"], k=TOP_K)
            rows.append(
                {
                    "q": case["q"],
                    "expect": case["expect"],
                    "rank": hit_rank(hits, case["expect"]),
                    "top_text": norm(hits[0]["text"])[:60] if hits else "",
                    "top_score": hits[0]["score"] if hits else 0.0,
                    "n": len(hits),
                }
            )
        except Exception as exc:
            rows.append(
                {"q": case["q"], "expect": case["expect"], "rank": None,
                 "top_text": f"ERROR: {exc}", "top_score": 0.0, "n": 0}
            )
    return rows


def summarise(rows: list[dict]) -> dict:
    top1 = sum(1 for r in rows if r["rank"] == 1)
    topk = sum(1 for r in rows if r["rank"] is not None)
    return {"top1": top1, "topk": topk, "total": len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", action="store_true",
                        help="(re)build both indexes before probing")
    parser.add_argument("--allow-fallback", action="store_true",
                        help="run even if embeddings fell back to hashing")
    args = parser.parse_args()

    from services.rag_service.embeddings import SemanticEmbeddings
    from services.rag_service.config import embedding_dimension

    status = SemanticEmbeddings(embedding_dimension()).status()
    print(f"embeddings: {status.get('active_backend')} ({status.get('model')})")
    if status.get("active_backend") != "sentence_transformers" and not args.allow_fallback:
        print(
            f"\nREFUSING TO RUN: embeddings fell back to "
            f"'{status.get('active_backend')}' - reason: {status.get('fallback_reason')}\n"
            "Hash embeddings have no semantic meaning, so a comparison on them says\n"
            "nothing about how either backend behaves in production. Run this inside\n"
            "the api container, or pass --allow-fallback to see mechanism-only results."
        )
        return 2

    results = {}
    for backend in ("opensearch", "neo4j"):
        print(f"\n=== {backend} ===")
        try:
            store = build_store(backend)
            if args.index:
                from services.rag_service.documents import load_knowledge_documents

                docs = load_knowledge_documents()
                print(f"indexing {len(docs)} chunks... {store.index_documents(docs, recreate=True)}")
            print(f"health: {store.health().get('index_exists', '?')} index present")
            results[backend] = probe(store)
        except Exception as exc:
            print(f"UNAVAILABLE: {exc}")
            results[backend] = None

    if not results.get("opensearch") or not results.get("neo4j"):
        print("\nCannot compare - one backend did not run.")
        return 1

    print("\n" + "=" * 100)
    print(f"{'question':52s} {'OS':>4s} {'NEO':>4s}  verdict")
    print("=" * 100)
    agree = same_rank = 0
    for os_row, neo_row in zip(results["opensearch"], results["neo4j"]):
        o, n = os_row["rank"], neo_row["rank"]
        if o == n:
            verdict = "same"
            same_rank += 1
            agree += 1
        elif o is not None and n is not None:
            verdict = f"both found, rank differs ({o}->{n})"
            agree += 1
        elif n is None:
            verdict = "*** NEO4J MISSED ***"
        else:
            verdict = "neo4j found, opensearch missed"
        print(f"{os_row['q'][:52]:52s} {str(o or '-'):>4s} {str(n or '-'):>4s}  {verdict}")

    os_sum, neo_sum = summarise(results["opensearch"]), summarise(results["neo4j"])
    total = len(PROBES)
    print("=" * 100)
    print(f"opensearch: top-1 {os_sum['top1']}/{total}   in top-{TOP_K} {os_sum['topk']}/{total}")
    print(f"neo4j     : top-1 {neo_sum['top1']}/{total}   in top-{TOP_K} {neo_sum['topk']}/{total}")
    print(f"identical rank on {same_rank}/{total}; both retrieved it on {agree}/{total}")
    if neo_sum["topk"] < os_sum["topk"]:
        print("\nNeo4j retrieves FEWER expected chunks - do not switch on this evidence.")
    elif neo_sum["top1"] < os_sum["top1"]:
        print("\nSame recall, worse ranking on Neo4j - weigh that against removing a container.")
    else:
        print("\nNeo4j matches or beats OpenSearch on this set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
