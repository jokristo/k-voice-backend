"""Generate numbered brochure paragraphs (style William Branham) from a sermon transcript."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)

BROCHURE_SYSTEM = """Tu es un éditeur de brochures de prédications chrétiennes (style William Branham).

Ta tâche : découper le texte en paragraphes logiques numérotés, SANS résumer ni omettre de contenu.

Règles :
1. Chaque paragraphe = un bloc de pensée cohérent (souvent 2 à 8 phrases).
2. Numérote à partir de 1 dans l'ordre du discours.
3. Conserve le texte intégral : ne supprime pas de passages, ne fusionne pas de manière à perdre du contenu.
4. Corrige légèrement la ponctuation si nécessaire, sans changer le sens.
5. Le français et le lingala du prédicateur sont conservés.
6. Pas de titres, pas de commentaires éditoriaux.

Réponds UNIQUEMENT en JSON valide."""

BROCHURE_JSON_HINT = """{
  "paragraphs": [
    {"number": 1, "text": "Premier paragraphe complet..."},
    {"number": 2, "text": "Deuxième paragraphe..."}
  ]
}"""

SECTION_CHARS = 14_000


class BrochureProcessingError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _split_sections(text: str, max_chars: int = SECTION_CHARS) -> list[str]:
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = text.rfind("\n\n", start, end)
            if cut <= start:
                cut = text.rfind(". ", start, end)
            if cut > start:
                end = cut + 1
        parts.append(text[start:end].strip())
        start = end
    return [p for p in parts if p]


def _parse_paragraphs(raw: str) -> list[dict[str, Any]]:
    data = json.loads(raw)
    rows = data.get("paragraphs") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise BrochureProcessingError("Format brochure invalide (paragraphs manquant)")
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        num = row.get("number")
        if not isinstance(num, int) or num < 1:
            num = i + 1
        out.append({"number": num, "text": text})
    if not out:
        raise BrochureProcessingError("Aucun paragraphe généré")
    return out


def _openai_client() -> OpenAI:
    if not settings.openai_api_key.strip():
        raise BrochureProcessingError("OPENAI_API_KEY requise pour les brochures")
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=max(120.0, float(settings.openai_nlp_timeout_s)),
    )


def _call_brochure_section(client: OpenAI, section: str, *, start_number: int) -> list[dict[str, Any]]:
    user = (
        f"Numérote les paragraphes à partir de {start_number} pour cette section du discours.\n\n"
        f"Format attendu :\n{BROCHURE_JSON_HINT}\n\n"
        f"Texte :\n{section}"
    )
    resp = client.chat.completions.create(
        model=settings.openai_summary_model,
        messages=[
            {"role": "system", "content": BROCHURE_SYSTEM},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=min(8192, settings.openai_nlp_summarize_max_tokens),
    )
    content = (resp.choices[0].message.content or "").strip()
    return _parse_paragraphs(content)


def _stub_paragraphs(text: str) -> list[dict[str, Any]]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    if len(blocks) <= 1 and len(text) > 400:
        sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
        blocks = []
        chunk: list[str] = []
        for s in sentences:
            chunk.append(s)
            if len(" ".join(chunk)) > 450:
                blocks.append(" ".join(chunk))
                chunk = []
        if chunk:
            blocks.append(" ".join(chunk))
    return [{"number": i + 1, "text": b} for i, b in enumerate(blocks) if b]


def generate_brochure_paragraphs(transcript: str) -> list[dict[str, Any]]:
    """Return [{number, text}, ...] for storage in sermon_outputs.brochure_paragraphs."""
    if not transcript or not transcript.strip():
        raise BrochureProcessingError("Transcription vide")

    use_openai = settings.nlp_provider == "openai" and bool(settings.openai_api_key.strip())
    if not use_openai:
        logger.warning("Brochure stub (pas de clé OpenAI)")
        return _stub_paragraphs(transcript)

    client = _openai_client()
    sections = _split_sections(transcript)
    merged: list[dict[str, Any]] = []
    next_num = 1
    for idx, section in enumerate(sections):
        try:
            rows = _call_brochure_section(client, section, start_number=next_num)
        except (APIConnectionError, APITimeoutError, RateLimitError, APIStatusError) as e:
            raise BrochureProcessingError(f"Erreur OpenAI brochure: {e}") from e
        for row in rows:
            merged.append({"number": next_num, "text": row["text"]})
            next_num += 1
        logger.info("brochure section=%s paragraphs=%s total=%s", idx + 1, len(rows), len(merged))
    return merged


def best_transcript_for_brochure(transcript: str, nlp_metadata: dict | None) -> str:
    if nlp_metadata and isinstance(nlp_metadata, dict):
        corrected = nlp_metadata.get("corrected_transcript")
        if isinstance(corrected, str) and corrected.strip():
            return corrected.strip()
    return transcript.strip()
