"""Tests unitaires — NLP (skip normalize, troncature)."""

from unittest.mock import patch

import pytest

from app.services.nlp_service import _normalize_transcript, _truncate


@patch("app.services.nlp_service.settings")
def test_truncate_under_limit(mock_settings):
    mock_settings.openai_nlp_max_transcript_chars = 100
    assert _truncate("abc") == "abc"


@patch("app.services.nlp_service.settings")
def test_truncate_over_limit(mock_settings):
    mock_settings.openai_nlp_max_transcript_chars = 10
    out = _truncate("0123456789012345")
    assert out.startswith("0123456789")
    assert "tronquée" in out


@patch("app.services.nlp_service.settings")
def test_normalize_skipped_when_too_long(mock_settings):
    mock_settings.openai_nlp_skip_full_normalize_chars = 100
    mock_settings.openai_nlp_max_transcript_chars = 100_000
    long_text = "x" * 200
    result = _normalize_transcript(long_text)
    assert result["normalize_skipped"] is True
    assert result["corrected_transcript"] == ""
