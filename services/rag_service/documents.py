import re
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


ROOT = Path(__file__).resolve().parents[2]

# The KB PDF stores every word as a separate text object, so pypdf emits "\n \n" between
# words (179 occurrences on page 1; 32% of the extracted text is whitespace). Collapsing
# runs of whitespace restores real words and sentences — without this, every split below
# operates on mangled text.
_WHITESPACE_RUN = re.compile(r"\s+")

# An FAQ answer ends where the next question begins, so "Q:" is the true topic boundary.
_QUESTION_MARKER = re.compile(r"(?=Q:)")


def load_knowledge_documents() -> list[Document]:
    return _split_documents(_load_pdf_kb())


def _load_markdown_kb() -> list[Document]:
    docs = []
    for path in (ROOT / "data" / "knowledge_base").glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
            if text.strip():
                docs.append(
                    Document(
                        page_content=text,
                        metadata={
                            "source": path.name,
                            "doc_type": "knowledge_base",
                            "document_version": str(int(path.stat().st_mtime)),
                        },
                    )
                )
        except Exception:
            pass
    return docs


def _load_pdf_kb() -> list[Document]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return []
    docs = []
    for path in (ROOT / "data" / "knowledge_base").glob("*.pdf"):
        try:
            reader = PdfReader(str(path))
            for page_num, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                if text.strip():
                    docs.append(
                        Document(
                            page_content=text,
                            metadata={
                                "source": f"{path.name}:p{page_num}",
                                "doc_type": "knowledge_base",
                                "document_version": str(int(path.stat().st_mtime)),
                            },
                        )
                    )
        except Exception:
            pass
    return docs


def _split_documents(documents: list[Document]) -> list[Document]:
    """One chunk per FAQ, falling back to character splitting for prose.

    The character splitter alone produced chunks spanning TWO unrelated FAQs (6 of 9),
    because the mangled whitespace above destroys the paragraph/sentence separators it
    looks for, leaving it to cut on raw character count. A chunk holding the tail of one
    answer plus the head of an unrelated question is genuinely partly-relevant to both
    topics, which is why one chunk scored ~0.62 against almost any question and why
    replies cited passages unrelated to the answer.

    Splitting on the "Q:" marker instead yields one complete question+answer per chunk.
    Documents with no markers (plain prose) keep the original character splitting.
    """
    faq_chunks: list[Document] = []
    prose: list[Document] = []
    # FAQ pairs run across page boundaries, so pages of the same file are joined before
    # splitting — otherwise a pair split by a page break stays split.
    for source, group in _group_by_file(documents).items():
        text = _WHITESPACE_RUN.sub(" ", " ".join(d.page_content for d in group)).strip()
        if not text:
            continue
        metadata = dict(group[0].metadata)
        metadata["source"] = source
        parts = [part.strip() for part in _QUESTION_MARKER.split(text) if part.strip()]
        # A single part means no "Q:" marker was found — not an FAQ document.
        if len(parts) <= 1:
            prose.append(Document(page_content=text, metadata=metadata))
            continue
        for part in parts:
            # Text before the first "Q:" is a title/heading, not a topic of its own.
            if not part.startswith("Q:"):
                continue
            faq_chunks.append(Document(page_content=part, metadata=dict(metadata)))

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    return faq_chunks + (splitter.split_documents(prose) if prose else [])


def _group_by_file(documents: list[Document]) -> dict[str, list[Document]]:
    """Group page-level documents back into their source file, order preserved.

    Page sources are "<file>.pdf:pN"; the ":pN" suffix is dropped so a chunk cites the
    document rather than a page number that no longer bounds it.
    """
    grouped: dict[str, list[Document]] = {}
    for document in documents:
        source = str(document.metadata.get("source", "unknown")).split(":p", 1)[0]
        grouped.setdefault(source, []).append(document)
    return grouped
