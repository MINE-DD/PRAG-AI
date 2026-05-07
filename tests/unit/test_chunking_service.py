from app.models.paper import ChunkType
from app.services.chunking_service import ChunkingService, classify_heading


def test_chunk_text_fixed_size():
    """Test fixed-size chunking"""
    service = ChunkingService(chunk_size=50, overlap=10)

    text = "This is a test text. " * 20  # Long text
    chunks = service.chunk_text(text)

    assert len(chunks) > 1
    for chunk in chunks[:-1]:  # All but last
        assert len(chunk) >= 40  # At least chunk_size - overlap


def test_chunk_text_with_overlap():
    """Test chunking with overlap"""
    service = ChunkingService(chunk_size=50, overlap=10)

    text = "A" * 100
    chunks = service.chunk_text(text)

    # Check overlap between consecutive chunks
    if len(chunks) > 1:
        assert chunks[0][-10:] == chunks[1][:10]


def test_chunk_short_text():
    """Test chunking text shorter than chunk_size"""
    service = ChunkingService(chunk_size=500, overlap=100)

    text = "Short text"
    chunks = service.chunk_text(text)

    assert len(chunks) == 1
    assert chunks[0] == text


# ---------------------------------------------------------------------------
# Markdown chunking
# ---------------------------------------------------------------------------

SAMPLE_MD = """# Introduction

This is the introduction paragraph. It sets the stage for the paper.

## Background

Some background information here about prior work and context.

More background text in a second paragraph.

## Methods

### Dataset

We used a large dataset of documents for our experiments.

### Model

The model architecture consists of multiple transformer layers.

# Results

The results show significant improvement over baselines.
"""


def test_markdown_chunk_returns_section_tuples():
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic")
    results = svc.chunk_markdown(SAMPLE_MD)
    assert all(isinstance(r, tuple) and len(r) == 2 for r in results)


def test_markdown_chunk_heading_not_in_text():
    """Heading is metadata only — chunk_text must NOT start with the heading."""
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic")
    results = svc.chunk_markdown(SAMPLE_MD)
    for chunk_text, heading in results:
        if heading:
            assert not chunk_text.startswith(heading)


def test_markdown_chunk_heading_stored_separately():
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic")
    results = svc.chunk_markdown(SAMPLE_MD)
    headings = [h for _, h in results]
    # Should have at least one non-empty heading
    assert any(h for h in headings)


def test_markdown_chunk_inherits_parent_heading():
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic")
    results = svc.chunk_markdown(SAMPLE_MD)
    heading_paths = [h for _, h in results if h]
    # The ### Dataset chunk should include ## Methods and ### Dataset but NOT the H1
    dataset_headings = [h for h in heading_paths if "Dataset" in h]
    assert dataset_headings, "Expected a chunk under ### Dataset"
    assert "## Methods" in dataset_headings[0]
    assert not dataset_headings[0].startswith("# ")


def test_markdown_chunk_no_headers():
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic")
    text = "Just a plain paragraph.\n\nAnother paragraph here."
    results = svc.chunk_markdown(text)
    assert len(results) >= 1
    assert all(heading == "" for _, heading in results)


def test_markdown_overflow_split():
    """Paragraphs exceeding chunk_size are split with overlap."""
    svc = ChunkingService(
        chunk_size=50, overlap=10, mode="markdown-academic", min_chunk_size=5
    )
    long_para = "word " * 40  # ~200 chars, well above chunk_size=50
    text = f"# Section\n\n{long_para}"
    results = svc.chunk_markdown(text)
    assert len(results) > 1
    for chunk_text, heading in results:
        assert heading == ""  # H1 is excluded from heading path
        assert len(chunk_text) <= 50


def test_markdown_merge_short_paragraphs():
    """Short paragraphs are merged with the next one."""
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic", min_chunk_size=100)
    text = "# Sec\n\nTiny.\n\nAlso tiny.\n\nA longer paragraph that has more content in it."
    results = svc.chunk_markdown(text)
    # The two tiny paragraphs should be merged together
    assert len(results) < 3


def test_chunk_text_markdown_mode_returns_strings():
    """chunk_text in markdown mode returns plain strings."""
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic")
    chunks = svc.chunk_text(SAMPLE_MD)
    assert all(isinstance(c, str) for c in chunks)


# ---------------------------------------------------------------------------
# classify_heading
# ---------------------------------------------------------------------------


def test_classify_heading_known_types():
    cases = [
        ("## **Abstract**", ChunkType.ABSTRACT),
        ("## ABSTRACT", ChunkType.ABSTRACT),
        ("## **1 Introduction**", ChunkType.INTRODUCTION),
        ("## INTRODUCTION", ChunkType.INTRODUCTION),
        ("## 2 Related Work", ChunkType.RELATED_WORK),
        ("## **3 Methods**", ChunkType.METHODS),
        ("## Materials and Methods", ChunkType.METHODS),
        ("## **2 Data**", ChunkType.DATA),
        ("## 5 Datasets", ChunkType.DATA),
        ("## **4 Results**", ChunkType.RESULTS),
        ("## 6 Evaluation", ChunkType.RESULTS),
        ("## **6 Discussion**", ChunkType.DISCUSSION),
        ("## DISCUSSION", ChunkType.DISCUSSION),
        ("## 7 Conclusion", ChunkType.CONCLUSION),
        ("## Limitations", ChunkType.CONCLUSION),
        ("## REFERENCES", ChunkType.REFERENCES),
        ("## References", ChunkType.REFERENCES),
        ("## Acknowledgements", ChunkType.ACKNOWLEDGEMENTS),
        ("## Funding", ChunkType.ACKNOWLEDGEMENTS),
        ("## Appendix A", ChunkType.APPENDIX),
        ("## Supplementary Material", ChunkType.APPENDIX),
        ("## Some Random Section", ChunkType.BODY),
        ("", ChunkType.BODY),
    ]
    for heading, expected in cases:
        result = classify_heading(heading)
        assert result == expected, (
            f"classify_heading({heading!r}) = {result!r}, expected {expected!r}"
        )


def test_classify_heading_strips_bold_and_numbers():
    assert classify_heading("## **3.2 Experimental Setup**") == ChunkType.METHODS
    assert classify_heading("## **5.1 Participating Systems**") == ChunkType.RESULTS


def test_chunk_by_paragraphs_legacy():
    """chunk_by_paragraphs splits on double newlines."""
    svc = ChunkingService()
    result = svc.chunk_by_paragraphs("para one\n\npara two\n\npara three")
    assert result == ["para one", "para two", "para three"]


def test_min_chunk_size_token_mode_default():
    """Token mode defaults min_chunk_size to 100 chars regardless of chunk_size."""
    svc = ChunkingService(chunk_size=512, mode="tokens")
    assert svc.min_chunk_size == 100


def test_min_chunk_size_explicit_overrides_mode():
    """Explicit min_chunk_size is always respected."""
    svc = ChunkingService(chunk_size=500, mode="markdown-academic", min_chunk_size=42)
    assert svc.min_chunk_size == 42


def test_references_chunks_not_merged():
    """Reference entries are emitted one per paragraph, not merged."""
    ref_body = "\n\n".join(f"[{i}] Author{i}, Title{i}." for i in range(10))
    text = f"# Paper\n\n## References\n\n{ref_body}"
    svc = ChunkingService(chunk_size=2000, mode="markdown-academic", min_chunk_size=500)
    results = svc.chunk_markdown(text)
    ref_chunks = [
        (t, h) for t, h in results if classify_heading(h) == ChunkType.REFERENCES
    ]
    assert len(ref_chunks) == 10  # one per entry, not merged despite min_chunk_size


def test_references_long_entry_is_overflow_split():
    """A reference entry longer than chunk_size is split, not emitted whole."""
    long_entry = "Word " * 60  # ~300 chars, above chunk_size=50
    text = f"# Paper\n\n## References\n\n{long_entry}"
    svc = ChunkingService(chunk_size=50, overlap=10, mode="markdown-academic")
    results = svc.chunk_markdown(text)
    ref_chunks = [
        (t, h) for t, h in results if classify_heading(h) == ChunkType.REFERENCES
    ]
    assert len(ref_chunks) > 1
    for chunk_text, _ in ref_chunks:
        assert len(chunk_text) <= 50


# ---------------------------------------------------------------------------
# truncate_to_tokens
# ---------------------------------------------------------------------------


def test_truncate_to_tokens_short_text_unchanged():
    """Text that already fits within max_tokens is returned as-is."""
    svc = ChunkingService()
    text = "Hello world, this is a short sentence."
    result = svc.truncate_to_tokens(text, max_tokens=512)
    assert result == text


def test_truncate_to_tokens_truncates_long_text():
    """Text exceeding max_tokens is truncated to fit."""
    svc = ChunkingService()
    long_text = "token " * 600  # well over 512 tokens
    result = svc.truncate_to_tokens(long_text, max_tokens=50)
    assert len(result) < len(long_text)
    token_count = len(svc.tokenizer.encode(result, add_special_tokens=False))
    assert token_count <= 50


def test_truncate_to_tokens_cyrillic_not_skipped():
    """Cyrillic text is always tokenized — the char-count fast path must not apply."""
    svc = ChunkingService()
    # 80 Cyrillic chars can easily tokenize to >100 tokens with byte-level BPE.
    cyrillic = "Привет мир это тест на русском языке слова " * 3  # ~130 chars
    # Verify that truncating at 30 tokens actually shortens the text.
    result = svc.truncate_to_tokens(cyrillic, max_tokens=30)
    token_count = len(svc.tokenizer.encode(result, add_special_tokens=False))
    assert token_count <= 30
