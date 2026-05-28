"""Tests fusion transcript."""

from app.services.transcript_merge import merge_transcript_chunks, _find_text_overlap


def test_merge_overlap_dedup():
    left = "Bonjour à tous. Le Seigneur est bon et sa miséricorde dure."
    right = "sa miséricorde dure à toujours. Amen frère."
    merged = merge_transcript_chunks([left, right])
    assert "miséricorde" in merged
    assert merged.count("miséricorde dure") == 1


def test_find_overlap_words():
    left = "alpha beta gamma delta epsilon"
    right = "gamma delta epsilon zeta eta"
    k = _find_text_overlap(left, right)
    assert k >= len("gamma delta epsilon") - 5


def test_merge_single():
    assert merge_transcript_chunks(["hello"]) == "hello"
