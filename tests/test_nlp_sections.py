"""Tests découpage sections map-reduce."""

from app.services.nlp_service import _split_into_sections


def test_split_small_unchanged():
    t = "Para one.\n\nPara two."
    parts = _split_into_sections(t, 5000)
    assert len(parts) == 1
    assert parts[0] == t


def test_split_multiple_sections():
    paras = ["P" * 3000 for _ in range(5)]
    t = "\n\n".join(paras)
    parts = _split_into_sections(t, 4000)
    assert len(parts) >= 2
    assert "".join(parts).replace("\n\n", "") == t.replace("\n\n", "")
