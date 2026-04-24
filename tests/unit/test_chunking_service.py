from app.services.chunking_service import ChunkingService


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
    svc = ChunkingService(chunk_size=2000, mode="markdown")
    results = svc.chunk_markdown(SAMPLE_MD)
    assert all(isinstance(r, tuple) and len(r) == 2 for r in results)


def test_markdown_chunk_heading_prefix_in_text():
    svc = ChunkingService(chunk_size=2000, mode="markdown")
    results = svc.chunk_markdown(SAMPLE_MD)
    for chunk_text, heading in results:
        if heading:
            assert chunk_text.startswith(heading)


def test_markdown_chunk_heading_stored_separately():
    svc = ChunkingService(chunk_size=2000, mode="markdown")
    results = svc.chunk_markdown(SAMPLE_MD)
    headings = [h for _, h in results]
    # Should have at least one non-empty heading
    assert any(h for h in headings)


def test_markdown_chunk_inherits_parent_heading():
    svc = ChunkingService(chunk_size=2000, mode="markdown")
    results = svc.chunk_markdown(SAMPLE_MD)
    heading_paths = [h for _, h in results if h]
    # The ### Dataset chunk should include both ## Methods and ### Dataset
    dataset_headings = [h for h in heading_paths if "Dataset" in h]
    assert dataset_headings, "Expected a chunk under ### Dataset"
    assert "## Methods" in dataset_headings[0]


def test_markdown_chunk_no_headers():
    svc = ChunkingService(chunk_size=2000, mode="markdown")
    text = "Just a plain paragraph.\n\nAnother paragraph here."
    results = svc.chunk_markdown(text)
    assert len(results) >= 1
    assert all(heading == "" for _, heading in results)


def test_markdown_overflow_split():
    """Paragraphs exceeding chunk_size are split with overlap."""
    svc = ChunkingService(chunk_size=50, overlap=10, mode="markdown", min_chunk_size=5)
    long_para = "word " * 40  # ~200 chars, well above chunk_size=50
    text = f"# Section\n\n{long_para}"
    results = svc.chunk_markdown(text)
    assert len(results) > 1
    for chunk_text, heading in results:
        assert heading == "# Section"
        assert len(chunk_text) <= 50 + len("# Section\n\n")


def test_markdown_merge_short_paragraphs():
    """Short paragraphs are merged with the next one."""
    svc = ChunkingService(chunk_size=2000, mode="markdown", min_chunk_size=100)
    text = "# Sec\n\nTiny.\n\nAlso tiny.\n\nA longer paragraph that has more content in it."
    results = svc.chunk_markdown(text)
    # The two tiny paragraphs should be merged together
    assert len(results) < 3


def test_chunk_text_markdown_mode_returns_strings():
    """chunk_text in markdown mode returns plain strings."""
    svc = ChunkingService(chunk_size=2000, mode="markdown")
    chunks = svc.chunk_text(SAMPLE_MD)
    assert all(isinstance(c, str) for c in chunks)
