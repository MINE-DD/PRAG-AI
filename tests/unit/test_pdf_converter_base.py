import pytest
from app.services.pdf_converter_base import PDFConverterBackend, get_converter, parse_authors


def test_parse_authors_simple():
    result = parse_authors("Alice Smith, Bob Jones")
    assert result == ["Alice Smith", "Bob Jones"]


def test_parse_authors_with_superscripts():
    result = parse_authors("Alice Smith 1,2*, Bob Jones 3†")
    assert result == ["Alice Smith", "Bob Jones"]


def test_parse_authors_filters_affiliations():
    result = parse_authors("Alice Smith, University of Testing, Bob Jones")
    assert len(result) == 2
    assert "University of Testing" not in result


def test_get_converter_unknown_raises():
    with pytest.raises(KeyError):
        get_converter("nonexistent_backend")
