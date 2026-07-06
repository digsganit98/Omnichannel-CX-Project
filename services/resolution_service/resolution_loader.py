import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from langchain_core.documents import Document
except Exception:
    @dataclass
    class Document:  # type: ignore[no-redef]
        page_content: str
        metadata: dict

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXAMPLES_PATH = ROOT / "data" / "resolution_kb" / "resolution_examples.json"

VALID_LEVELS = {"L1", "L2", "L3"}


@dataclass(frozen=True)
class ResolutionExample:
    customer_query: str
    intent: str
    resolution_level: str
    reason: str

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "ResolutionExample":
        return cls(
            customer_query=str(item.get("customer_query", "")).strip(),
            intent=str(item.get("intent", "")).strip(),
            resolution_level=str(item.get("resolution_level", "")).strip().upper(),
            reason=str(item.get("reason", "")).strip(),
        )

    def to_search_text(self) -> str:
        return (
            f"Customer Query: {self.customer_query}\n"
            f"Intent: {self.intent}\n"
            f"Resolution Level: {self.resolution_level}\n"
            f"Reason: {self.reason}"
        )

    def to_prompt_dict(self) -> dict[str, str]:
        return {
            "customer_query": self.customer_query,
            "intent": self.intent,
            "resolution_level": self.resolution_level,
            "reason": self.reason,
        }


class ResolutionExampleLoader:
    """Loads curated L1/L2/L3 examples used for semantic retrieval and few-shot prompting."""

    def __init__(self, file_path: Path | None = None) -> None:
        self.file_path = file_path or DEFAULT_EXAMPLES_PATH

    def load_examples(self) -> list[ResolutionExample]:
        if not self.file_path.exists():
            logger.warning("resolution_examples_missing", extra={"path": str(self.file_path)})
            return []

        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("resolution_examples_load_failed", extra={"path": str(self.file_path), "error": str(exc)})
            return []

        if not isinstance(raw, list):
            logger.warning("resolution_examples_invalid_shape", extra={"path": str(self.file_path)})
            return []

        examples: list[ResolutionExample] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            example = ResolutionExample.from_dict(item)
            if example.customer_query and example.resolution_level in VALID_LEVELS:
                examples.append(example)
        return examples

    def load_documents(self) -> list[Document]:
        documents: list[Document] = []
        for index, example in enumerate(self.load_examples()):
            documents.append(
                Document(
                    page_content=example.to_search_text(),
                    metadata={
                        "source": f"resolution_example_{index}",
                        "doc_type": "resolution_example",
                        "intent": example.intent,
                        "resolution_level": example.resolution_level,
                        "reason": example.reason,
                    },
                )
            )
        return documents


def load_resolution_examples() -> list[ResolutionExample]:
    return ResolutionExampleLoader().load_examples()


def load_resolution_documents() -> list[Document]:
    return ResolutionExampleLoader().load_documents()
