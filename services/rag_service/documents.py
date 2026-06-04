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
        reader = PdfReader(str(path))
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": path.name,
                        "page": page_num,
                        "doc_type": "knowledge_base",
                        "document_format": "pdf",
                        "document_version": str(int(path.stat().st_mtime)),
                    },
                )
            )
    return docs


def _split_documents(documents: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    return splitter.split_documents(documents)
