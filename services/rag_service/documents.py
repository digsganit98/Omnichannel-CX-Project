from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


ROOT = Path(__file__).resolve().parents[2]


def load_knowledge_documents() -> list[Document]:
    return _split_documents(_load_markdown_kb())


def _load_markdown_kb() -> list[Document]:
    docs = []
    for path in (ROOT / "data" / "knowledge_base").glob("*.md"):
        docs.append(
            Document(
                page_content=path.read_text(encoding="utf-8"),
                metadata={
                    "source": path.name,
                    "doc_type": "knowledge_base",
                    "document_version": str(int(path.stat().st_mtime)),
                },
            )
        )
    return docs


def _split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    return splitter.split_documents(documents)
