"""Tests parsing JSON NLP."""

import pytest

from app.services.nlp_service import NLPProcessingError, _extract_json_object, _parse_json_content


def test_parse_json_plain():
    data = _parse_json_content('{"central_message": "foi", "summary": "texte"}')
    assert data["central_message"] == "foi"


def test_parse_json_markdown_fence():
    raw = '```json\n{"summary": "ok", "key_points": []}\n```'
    data = _parse_json_content(raw)
    assert data["summary"] == "ok"


def test_parse_json_invalid_raises():
    with pytest.raises(NLPProcessingError, match="JSON invalide"):
        _parse_json_content('{"summary": "coupe en plein milieu')


def test_extract_json_object():
    assert _extract_json_object('voici {"a": 1} fin') == '{"a": 1}'
