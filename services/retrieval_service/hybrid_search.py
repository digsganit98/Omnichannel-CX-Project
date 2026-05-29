from dataclasses import dataclass
from pathlib import Path


@dataclass
class SearchResult:
    answer: str
    source: str
    score: float


class HybridSearch:
    def __init__(self, knowledge_base_dir: str | Path = "data/knowledge_base") -> None:
        self.knowledge_base_dir = Path(knowledge_base_dir)

    def search(self, query: str) -> SearchResult | None:
        docs = list(self.knowledge_base_dir.glob("*.md"))
        if not docs:
            return None

        query_terms = {term.strip(".,!?").lower() for term in query.split() if len(term) > 2}
        best: tuple[float, Path, str] | None = None
        for doc in docs:
            text = doc.read_text(encoding="utf-8")
            lowered = text.lower()
            overlap = sum(1 for term in query_terms if term in lowered)
            score = overlap / max(len(query_terms), 1)
            if best is None or score > best[0]:
                best = (score, doc, text)

        if best is None or best[0] <= 0:
            return None

        answer = self._extract_answer(best[2], query_terms)
        return SearchResult(answer=answer, source=best[1].name, score=round(best[0], 2))

    def _extract_answer(self, text: str, query_terms: set[str]) -> str:
        paragraphs = [
            part.strip()
            for part in text.split("\n\n")
            if part.strip() and not part.strip().startswith("#")
        ]
        for paragraph in paragraphs:
            lowered = paragraph.lower()
            if any(term in lowered for term in query_terms):
                return paragraph
        return paragraphs[0]
