from dataclasses import dataclass
from pathlib import Path

from services.rag_service.documents import load_knowledge_documents

STOPWORDS = {
    "and", "are", "can", "for", "how", "the", "this", "that", "what", "when",
    "where", "which", "who", "why", "with", "you", "your", "have", "should",
    "would", "could", "will", "shall", "need", "doing", "about", "from",
}

EXPANSIONS = {
    "stolen": {"lost", "block", "blocked"},
    "lost": {"stolen", "block", "blocked"},
    "card": {"debit", "credit"},
    "debit": {"card"},
    "credit": {"card"},
    "kyc": {"documents", "identity", "address"},
    "emi": {"loan", "repayment"},
}


@dataclass
class SearchResult:
    answer: str
    source: str
    score: float


class HybridSearch:
    def __init__(self, knowledge_base_dir: str | Path = "data/knowledge_base") -> None:
        self.knowledge_base_dir = Path(knowledge_base_dir)

    def search(self, query: str) -> SearchResult | None:
        docs = self._load_documents()
        if not docs:
            return None

        query_terms = self.query_terms(query)
        best: tuple[float, str, str] | None = None
        for source, text in docs:
            for snippet in self._snippets(text):
                score = self.score_text(query, snippet, query_terms)
                if best is None or score > best[0]:
                    best = (score, source, snippet)

        if best is None or best[0] <= 0:
            return None

        return SearchResult(answer=best[2], source=best[1], score=round(min(best[0], 1.0), 2))

    @classmethod
    def query_terms(cls, query: str) -> set[str]:
        terms = {
            term.strip(".,!?;:()[]{}\"'").lower()
            for term in query.split()
            if len(term.strip(".,!?;:()[]{}\"'")) > 2
        }
        terms = {term for term in terms if term not in STOPWORDS}
        expanded = set(terms)
        for term in terms:
            expanded.update(EXPANSIONS.get(term, set()))
        return expanded

    @classmethod
    def score_text(cls, query: str, text: str, query_terms: set[str] | None = None) -> float:
        terms = query_terms or cls.query_terms(query)
        if not terms:
            return 0.0
        lowered = text.lower()
        overlap = sum(1 for term in terms if term in lowered)
        phrase_bonus = 0.0
        if "stolen" in terms and "lost or stolen" in lowered:
            phrase_bonus += 0.5
        if "card" in terms and ("debit/credit card" in lowered or "credit card" in lowered):
            phrase_bonus += 0.3
        return (overlap + phrase_bonus) / max(len(terms), 1)

    def _load_documents(self) -> list[tuple[str, str]]:
        if self.knowledge_base_dir == Path("data/knowledge_base"):
            return [
                (document.metadata.get("source", "unknown"), document.page_content)
                for document in load_knowledge_documents()
            ]
        return [
            (path.name, path.read_text(encoding="utf-8"))
            for path in self.knowledge_base_dir.glob("*.md")
        ]

    @staticmethod
    def _snippets(text: str) -> list[str]:
        normalized = " ".join(text.split())
        snippets: list[str] = []
        questions = normalized.split("Q:")
        for item in questions:
            item = item.strip()
            if not item:
                continue
            qa = "Q: " + item
            next_question = qa.find(" Q:", 3)
            if next_question > -1:
                qa = qa[:next_question]
            snippets.append(qa.strip())
        if snippets:
            return snippets
        return [
            part.strip()
            for part in text.split("\n\n")
            if part.strip() and not part.strip().startswith("#")
        ] or [normalized]
