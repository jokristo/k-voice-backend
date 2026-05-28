"""Validation schéma résumé NLP."""

import pytest

from app.services.nlp_service import (
    NLPProcessingError,
    _reject_wrong_summarize_schema,
    _validate_body_summarize,
    _validate_full_summarize,
    _validate_meta_summarize,
)


def test_reject_corrected_transcript_in_summarize():
    with pytest.raises(NLPProcessingError, match="recopié"):
        _reject_wrong_summarize_schema({"corrected_transcript": "x" * 500})


def test_validate_full_ok():
    _validate_full_summarize({"central_message": "foi", "summary": "texte court"})


def test_validate_meta_rejects_summary():
    with pytest.raises(NLPProcessingError, match="summary"):
        _validate_meta_summarize({"central_message": "ok", "summary": "un long résumé ici"})


def test_validate_body_requires_summary():
    with pytest.raises(NLPProcessingError, match="summary"):
        _validate_body_summarize({"central_message": "only meta"})
