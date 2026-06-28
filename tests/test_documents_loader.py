"""Tests for the KB document loader — verifies markdown is now indexed (Phase 2 fix)."""

from services.rag_service import documents


def test_load_knowledge_documents_includes_markdown(tmp_path, monkeypatch):
    """A .md file in the knowledge_base dir must be picked up by load_knowledge_documents().

    Phase 1 loaded PDF only; the Phase 2 fix wires in _load_markdown_kb().
    """
    kb_dir = tmp_path / "data" / "knowledge_base"
    kb_dir.mkdir(parents=True)
    (kb_dir / "sample_topic.md").write_text(
        "# Sample Topic\n\nQ: Is markdown indexed?\nA: Yes, it should be.\n",
        encoding="utf-8",
    )
    # Point the loader's ROOT at our temp tree so it globs the temp KB dir.
    monkeypatch.setattr(documents, "ROOT", tmp_path)

    docs = documents.load_knowledge_documents()

    assert docs, "expected at least one chunk from the markdown file"
    sources = {d.metadata.get("source") for d in docs}
    assert "sample_topic.md" in sources
    # All KB docs must carry doc_type=knowledge_base so they pass the customer-safe filter.
    assert all(d.metadata.get("doc_type") == "knowledge_base" for d in docs)


def test_load_markdown_kb_skips_empty_files(tmp_path, monkeypatch):
    kb_dir = tmp_path / "data" / "knowledge_base"
    kb_dir.mkdir(parents=True)
    (kb_dir / "empty.md").write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(documents, "ROOT", tmp_path)

    docs = documents.load_knowledge_documents()

    assert all(d.metadata.get("source") != "empty.md" for d in docs)
