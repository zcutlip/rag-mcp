"""Tests for ingest filtering via ordered patterns (issue #4) — RED phase."""

from unittest.mock import patch

from rag_mcp.ingest import should_include, sync_directory
from rag_mcp.store import VectorStore

EMBEDDINGS_HOST = "http://localhost:11434"
EMBEDDINGS_MODEL = "nomic-embed-text"


def _fake_embeddings(texts, host, model):
    return [[0.1, 0.2] for _ in texts]


# --- should_include unit tests (10) ---


def test_should_include_empty_list_includes_everything():
    """Empty pattern list includes everything."""
    assert should_include("anything.md", []) is True
    assert should_include("docs/a.md", []) is True
    assert should_include("private/secret.md", []) is True


def test_should_include_default_include_when_no_match():
    """No pattern matches → default included."""
    assert should_include("other/file.md", ["docs/**"]) is True
    assert should_include("a.md", ["nomatch/**"]) is True
    assert should_include("public/a.md", ["!private/**"]) is True


def test_should_include_whitelists_docs():
    """Whitelist pattern includes matching paths."""
    assert should_include("docs/a.md", ["docs/**"]) is True
    assert should_include("docs/nested/b.md", ["docs/**"]) is True


def test_should_include_negation_excludes():
    """Negated pattern excludes matching paths."""
    assert should_include("private/a.md", ["!private/**"]) is False
    assert should_include("private/nested/b.md", ["!private/**"]) is False
    assert should_include("other/a.md", ["!private/**"]) is True


def test_should_include_last_match_wins_rescue():
    """Last match wins: rescue via ordered patterns."""
    patterns = ["private/**", "!private/keep/**"]
    # private/a.md matches first only → included
    assert should_include("private/a.md", patterns) is True
    # private/keep/a.md matches both → last (!private/keep/**) wins → excluded
    assert should_include("private/keep/a.md", patterns) is False


def test_should_include_last_match_wins_multiple():
    """Multiple ordered patterns — final match determines result."""
    patterns = ["a/**", "!a/b/**", "a/b/c/**"]
    assert should_include("a/b/c/d.md", patterns) is True
    assert should_include("a/b/d.md", patterns) is False
    assert should_include("a/x.md", patterns) is True


def test_should_include_whitelist_with_carveout():
    """Whitelist with carveout: docs/** but not drafts."""
    patterns = ["docs/**", "!**/draft-*"]
    assert should_include("docs/a.md", patterns) is True
    assert should_include("docs/draft-a.md", patterns) is False
    assert should_include("docs/nested/draft-note.md", patterns) is False
    assert should_include("docs/keep.md", patterns) is True


def test_should_include_case_insensitive():
    """Matching is case-insensitive."""
    assert should_include("Docs/A.MD", ["docs/**"]) is True
    assert should_include("PRIVATE/secret.md", ["!private/**"]) is False
    assert should_include("DOCS/DRAFT-a.md", ["docs/**", "!**/draft-*"]) is False


def test_should_include_star_crosses_directories():
    """'*' crosses '/' — ['*.md'] matches 'docs/a.md'."""
    assert should_include("docs/a.md", ["*.md"]) is True
    assert should_include("a.md", ["*.md"]) is True
    assert should_include("docs/nested/b.md", ["*.md"]) is True


def test_should_include_double_star_same_as_single():
    """'**' is equivalent to '*'."""
    assert should_include("docs/a.md", ["docs/**"]) == should_include(
        "docs/a.md", ["docs/*"]
    )
    assert should_include("docs/a.md", ["**/*.md"]) == should_include(
        "docs/a.md", ["*.md"]
    )
    assert should_include("a.md", ["**"]) == should_include("a.md", ["*"])


# --- sync_directory integration tests (5) ---


def test_sync_patterns_exclude_subtree_first_sync(tmp_path):
    """First sync with blacklist excludes private subtree."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("hello world")
    (docs_dir / "b.md").write_text("another doc")
    private = docs_dir / "private"
    private.mkdir()
    (private / "secret.md").write_text("secret content")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
            patterns=["!private/**"],
        )

    assert result["added"] == 2
    meta = store.get_all_metadata("test")
    sources = {m["source"] for m in meta["metadatas"]}
    assert sources == {"a.md", "b.md"}
    assert "private/secret.md" not in sources
    # only included docs were embedded
    called = mock_emb.call_args.args[0] if mock_emb.call_args else []
    assert "hello world" in called
    assert "another doc" in called
    assert "secret content" not in called


def test_sync_patterns_excluded_never_embedded(tmp_path):
    """Excluded files never hit Ollama."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "included.md").write_text("included content")
    private = docs_dir / "private"
    private.mkdir()
    (private / "excluded.md").write_text("excluded content")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
            patterns=["!private/**"],
        )

    assert mock_emb.call_count == 1
    called_texts = mock_emb.call_args.args[0]
    assert called_texts == ["included content"]
    assert "excluded content" not in called_texts


def test_sync_patterns_newly_excluded_deleted_on_resync(tmp_path):
    """File that becomes excluded is deleted from index via seen_sources diff."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("hello")
    private = docs_dir / "private"
    private.mkdir()
    secret = private / "secret.md"
    secret.write_text("secret")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
        )
    meta = store.get_all_metadata("test")
    assert len(meta["ids"]) == 2

    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
            patterns=["!private/**"],
        )

    assert result["deleted"] == 1
    meta = store.get_all_metadata("test")
    sources = {m["source"] for m in meta["metadatas"]}
    assert "private/secret.md" not in sources
    assert "a.md" in sources
    mock_emb.assert_not_called()


def test_sync_patterns_removing_exclusion_restores(tmp_path):
    """Removing an exclusion re-adds previously excluded file."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("hello")
    private = docs_dir / "private"
    private.mkdir()
    secret = private / "secret.md"
    secret.write_text("secret")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings):
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
            patterns=["!private/**"],
        )
    meta = store.get_all_metadata("test")
    assert len(meta["ids"]) == 1
    assert meta["metadatas"][0]["source"] == "a.md"

    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        result = sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
            patterns=None,
        )

    assert result["added"] == 1
    meta = store.get_all_metadata("test")
    sources = {m["source"] for m in meta["metadatas"]}
    assert "private/secret.md" in sources
    assert "a.md" in sources
    assert mock_emb.call_count == 1
    assert mock_emb.call_args.args[0] == ["secret"]


def test_sync_patterns_whitelist_mode(tmp_path):
    """Whitelist patterns include only matching files."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("hello")
    docs_sub = docs_dir / "docs"
    docs_sub.mkdir()
    (docs_sub / "inside.md").write_text("inside docs")
    other = docs_dir / "other"
    other.mkdir()
    (other / "outside.md").write_text("outside")

    store = VectorStore(persist_dir=str(tmp_path / "chroma"))
    with patch("rag_mcp.ingest.get_embeddings", side_effect=_fake_embeddings) as mock_emb:
        sync_directory(
            store,
            str(docs_dir),
            collection="test",
            embeddings_host=EMBEDDINGS_HOST,
            embeddings_model=EMBEDDINGS_MODEL,
            patterns=["docs/**"],
        )

    meta = store.get_all_metadata("test")
    sources = {m["source"] for m in meta["metadatas"]}
    assert "docs/inside.md" in sources
    assert "other/outside.md" not in sources
    assert "a.md" not in sources
    called = mock_emb.call_args.args[0] if mock_emb.call_args else []
    assert "inside docs" in called
    assert "outside" not in called
    assert "hello" not in called
