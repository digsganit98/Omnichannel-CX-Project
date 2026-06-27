import json
from pathlib import Path
from typing import List

from langchain_core.documents import Document


ROOT = Path(__file__).resolve().parents[2]


class ResolutionDocumentLoader:
    """
    Loads resolution_examples.json and converts it into LangChain Documents
    for OpenSearch indexing.
    """

    def __init__(self) -> None:
        self.file_path = ROOT / "data" / "resolution_kb" / "resolution_examples.json"

    def load(self) -> List[Document]:
        if not self.file_path.exists():
            return []

        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        documents: List[Document] = []

        for idx, item in enumerate(data):
            text = self._format_example(item)

            metadata = {
                "source": f"resolution_example_{idx}",
                "doc_type": "resolution_examples",
                "intent": item.get("intent", ""),
                "resolution_level": item.get("resolution_level", ""),
            }

            documents.append(
                Document(
                    page_content=text,
                    metadata=metadata,
                )
            )

        return documents

    def _format_example(self, item: dict) -> str:
        """
        Converts JSON example into searchable text for embeddings.
        """

        return (
            f"Customer Query: {item.get('customer_query', '')}\n"
            f"Intent: {item.get('intent', '')}\n"
            f"Resolution Level: {item.get('resolution_level', '')}\n"
            f"Reason: {item.get('reason', '')}"
        )