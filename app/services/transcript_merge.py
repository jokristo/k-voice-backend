"""Fusion intelligente des transcripts Whisper (overlap + jonctions)."""

import logging
import re
from typing import List, Tuple  # noqa: F401 — Tuple used in _merge_two_transcripts

logger = logging.getLogger(__name__)

_MIN_OVERLAP_CHARS = 40
_MAX_SEARCH_CHARS = 4000


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _tokenize_words(text: str) -> List[str]:
    return [re.sub(r"[^\w]", "", w, flags=re.UNICODE).lower() for w in text.split() if re.search(r"\w", w)]


def _find_text_overlap(left: str, right: str) -> int:
    """
    Longueur k telle que left[-k:] ≈ right[:k] (suffixe / préfixe).
    Recherche du plus grand k >= _MIN_OVERLAP_CHARS.
    """
    left_tail = left[-_MAX_SEARCH_CHARS:] if len(left) > _MAX_SEARCH_CHARS else left
    right_head = right[:_MAX_SEARCH_CHARS] if len(right) > _MAX_SEARCH_CHARS else right
    max_k = min(len(left_tail), len(right_head), 2500)
    left_l = left_tail.lower()
    right_l = right_head.lower()

    for k in range(max_k, _MIN_OVERLAP_CHARS - 1, -1):
        a = left_l[-k:].strip()
        b = right_l[:k].strip()
        if a and b and (a == b or a in b or b in a):
            return k

    left_words = _tokenize_words(left_tail)
    right_words = _tokenize_words(right_head)
    max_words = min(80, len(left_words), len(right_words))
    for n in range(max_words, 2, -1):
        if left_words[-n:] == right_words[:n]:
            # Position char du début du chevauchement dans right (approx.)
            phrase = " ".join(left_tail.split()[-n:])
            pos = right.find(right_head.split()[0] if right_head.split() else "")
            # Recaler sur la phrase rejointe dans left
            idx = left.rfind(phrase[: max(20, len(phrase) // 2)])
            if idx >= 0:
                return len(left) - idx
            return len(" ".join(left_tail.split()[-n:]))
    return 0


def _smooth_boundary(left: str, right: str) -> str:
    """Joint deux morceaux quand l'overlap n'a pas été détecté."""
    left = left.rstrip()
    right = right.lstrip()
    if not left:
        return right
    if not right:
        return left
    # Phrase coupée : pas de ponctuation finale + suite en minuscule
    if left[-1].isalnum() and right[0].islower():
        return f"{left} {right}"
    if left[-1] in ".!?…:":
        return f"{left}\n\n{right}"
    return f"{left} {right}"


def _merge_two_transcripts(left: str, right: str) -> Tuple[str, int]:
    """Fusionne deux morceaux ; retourne (texte, chars de overlap utilisés)."""
    overlap = _find_text_overlap(left, right)
    if overlap > 0 and overlap < len(right):
        return left + right[overlap:].lstrip(), overlap

    # Chevauchement par mots : suffixe gauche = préfixe droit
    lw = _tokenize_words(left[-3000:])
    rw = _tokenize_words(right[:3000])
    for n in range(min(len(lw), len(rw), 60), 2, -1):
        if lw[-n:] == rw[:n]:
            # Retirer les n premiers mots de right (version brute)
            raw_right_words = right.split()
            trimmed = " ".join(raw_right_words[n:])
            return _smooth_boundary(left, trimmed), n

    return _smooth_boundary(left, right), 0


def merge_transcript_chunks(chunks: List[str]) -> str:
    """Fusionne les transcripts de morceaux avec dédoublonnage d'overlap."""
    cleaned = [c.strip() for c in chunks if c and c.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]

    merged = cleaned[0]
    for i, nxt in enumerate(cleaned[1:], start=2):
        merged, used = _merge_two_transcripts(merged, nxt)
        logger.info(
            "transcript merge chunk=%s overlap_used=%s merged_len=%s",
            i,
            used,
            len(merged),
        )

    return merged


def whisper_continuation_prompt(base_hint: str, previous_transcript: str, max_tail_chars: int) -> str:
    """Prompt Whisper : termes bibliques + fin du segment précédent."""
    tail = previous_transcript.strip()
    if not tail:
        return base_hint
    if len(tail) > max_tail_chars:
        # Couper au dernier espace pour éviter un mot tronqué
        tail = tail[-max_tail_chars:]
        sp = tail.find(" ")
        if sp > 0:
            tail = tail[sp + 1 :]
    return (
        f"{base_hint}\n\n"
        "Contexte — fin du segment précédent (continuer la transcription, ne pas répéter ce passage) :\n"
        f"{tail}"
    )
