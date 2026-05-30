"""Stabilité NLP — garde-fous normalisation vs résumé."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.nlp_service import (
    NLPProcessingError,
    _looks_like_normalize_output,
    _normalize_transcript,
    _openai_json_call,
    _prose_looks_like_recopy,
    _summarize_safe_pipeline,
)


def test_looks_like_normalize_detects_corrected_transcript():
    assert _looks_like_normalize_output('{"corrected_transcript": "Bonjour"}')


def test_prose_recopy_detection():
    src = "A" * 500 + " message pastoral long."
    copy = src + " suite identique " + "B" * 200
    assert _prose_looks_like_recopy(copy, src) is True
    assert _prose_looks_like_recopy("Résumé court du sermon.", src) is False


@patch("app.services.nlp_service._get_openai_client")
@patch("app.services.nlp_service.settings")
def test_json_call_normalize_allows_corrected_transcript(mock_settings, mock_client_factory):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_summary_model = "gpt-4o-mini"
    mock_settings.openai_nlp_json_retry_attempts = 1

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"corrected_transcript": "texte corrigé", "corrections": [], "confidence": "high"}'
            ),
            finish_reason="stop",
        )
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_client_factory.return_value = mock_client

    data = _openai_json_call(
        "system",
        "user",
        purpose="normalize",
    )
    assert data["corrected_transcript"] == "texte corrigé"


@patch("app.services.nlp_service._get_openai_client")
@patch("app.services.nlp_service.settings")
def test_json_call_summarize_rejects_normalize_shaped(mock_settings, mock_client_factory):
    mock_settings.openai_api_key = "sk-test"
    mock_settings.openai_summary_model = "gpt-4o-mini"
    mock_settings.openai_nlp_json_retry_attempts = 1

    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(
            message=MagicMock(
                content='{"corrected_transcript": "Bonjour à tous dans cette prédication"}'
            ),
            finish_reason="stop",
        )
    ]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    mock_client_factory.return_value = mock_client

    with pytest.raises(NLPProcessingError, match="repli automatique"):
        _openai_json_call("system", "user", purpose="summarize")


@patch("app.services.nlp_service._openai_prose_call")
@patch("app.services.nlp_service._openai_json_call")
@patch("app.services.nlp_service.settings")
def test_safe_pipeline_single_json_success_one_call(mock_settings, mock_json, mock_prose):
    mock_settings.openai_nlp_max_transcript_chars = 100_000
    mock_settings.openai_nlp_summarize_max_input_chars = 28_000
    mock_settings.openai_nlp_summarize_max_tokens = 4096

    mock_json.return_value = {
        "central_message": "La foi",
        "summary": "Résumé complet en un JSON.",
        "key_points": ["point 1"],
        "main_themes": ["foi"],
        "key_verses": [],
        "references": [],
    }

    result = _summarize_safe_pipeline("Bonjour. " * 50)
    assert result["summary"] == "Résumé complet en un JSON."
    assert result["_pipeline_mode"] == "single-json"
    mock_json.assert_called_once()
    mock_prose.assert_not_called()


@patch("app.services.nlp_service._openai_prose_call")
@patch("app.services.nlp_service._openai_json_call")
@patch("app.services.nlp_service.settings")
def test_safe_pipeline_json_fail_then_one_prose_only(mock_settings, mock_json, mock_prose):
    mock_settings.openai_nlp_max_transcript_chars = 100_000
    mock_settings.openai_nlp_summarize_max_input_chars = 28_000
    mock_settings.openai_nlp_summarize_max_tokens = 4096
    mock_settings.openai_nlp_summarize_body_max_tokens = 2800

    mock_json.side_effect = NLPProcessingError("Réponse de normalisation au lieu du résumé — repli automatique.")
    mock_prose.return_value = "Résumé pastoral généré."

    result = _summarize_safe_pipeline("Bonjour. " * 50)
    assert result["summary"] == "Résumé pastoral généré."
    assert result["_pipeline_mode"] == "prose-fallback"
    mock_json.assert_called_once()
    mock_prose.assert_called_once()


@patch("app.services.nlp_service._openai_json_call")
@patch("app.services.nlp_service.settings")
def test_normalize_failure_returns_skip(mock_settings, mock_json):
    mock_settings.openai_nlp_skip_full_normalize_chars = 25_000
    mock_settings.openai_nlp_max_transcript_chars = 100_000
    mock_settings.openai_nlp_normalize_max_tokens = 4096
    mock_json.side_effect = NLPProcessingError("Erreur API")

    result = _normalize_transcript("texte court de prédication.")
    assert result["normalize_skipped"] is True
    assert result["corrected_transcript"] == ""
