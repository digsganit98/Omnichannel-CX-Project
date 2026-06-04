from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]


def load_knowledge_documents() -> list[Document]:
    return _split_documents(_load_pdf_kb())


def _load_pdf_kb() -> list[Document]:
    docs = []
    for path in (ROOT / "data" / "knowledge_base").glob("*.pdf"):
        docs.append(
            Document(
                page_content=extract_pdf_text(path),
                metadata={
                    "source": path.name,
                    "doc_type": "knowledge_base",
                    "document_format": "pdf",
                    "document_version": str(int(path.stat().st_mtime)),
                },
            )
        )
    return docs


def extract_pdf_text(path: str | Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page.strip() for page in pages if page.strip())


def _split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    return splitter.split_documents(documents)
