import pytest

from app.services.brochure_service import (
    BrochureProcessingError,
    _parse_paragraphs,
    _stub_paragraphs,
)


def test_parse_paragraphs_valid():
    rows = _parse_paragraphs(
        '{"paragraphs":[{"number":1,"text":"Premier"},{"number":2,"text":"Deuxième"}]}'
    )
    assert len(rows) == 2
    assert rows[0]["text"] == "Premier"


def test_parse_paragraphs_markdown_fence():
    raw = '```json\n{"paragraphs":[{"number":1,"text":"A"}]}\n```'
    assert _parse_paragraphs(raw)[0]["text"] == "A"


def test_parse_paragraphs_trailing_comma_repair():
    raw = '{"paragraphs":[{"number":1,"text":"B",},]}'
    assert _parse_paragraphs(raw)[0]["text"] == "B"


def test_parse_paragraphs_invalid_raises():
    with pytest.raises(BrochureProcessingError, match="JSON brochure invalide"):
        _parse_paragraphs("not json at all")


def test_stub_paragraphs_splits_sentences():
    text = "Première phrase longue. " * 80
    rows = _stub_paragraphs(text)
    assert len(rows) >= 2
    assert rows[0]["number"] == 1
