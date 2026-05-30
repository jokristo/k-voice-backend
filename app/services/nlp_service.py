import json
import logging
import re
from typing import Any, Callable, Dict, List, Literal, Optional

JsonCallPurpose = Literal["normalize", "summarize"]

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Étape 1 — Normalisation (correction ASR, FR + lingala, termes bibliques)
# ---------------------------------------------------------------------------

NORMALIZE_SYSTEM_PROMPT = """Tu es un pasteur congolais expérimenté, trilingue en français et familiarisé avec le lingala liturgique.
Tu reçois une transcription automatique (ASR) d'une prédication chrétienne.

Ta SEULE tâche : produire une version corrigée et lisible du texte, sans résumer.

Règles strictes :
1. Corrige les erreurs ASR sur les noms bibliques (Ecclésiaste, Genèse, Ésaïe, Romains, Corinthiens, Psaumes, etc.).
2. La prédication peut mélanger français et lingala : CONSERVE le lingala tel quel.
3. Si un passage lingala peut prêter à confusion, ajoute une glose courte entre crochets en français : [glose].
4. Ne traduis pas tout le lingala en français — respecte la voix du prédicateur.
5. N'invente AUCUN verset ni citation biblique absente du texte.
6. Ne résume pas, ne commente pas : uniquement corriger et clarifier le texte parlé.
7. Conserve les paragraphes et la structure du discours.

Réponds UNIQUEMENT en JSON valide."""

NORMALIZE_JSON_HINT = """{
  "corrected_transcript": "texte corrigé complet",
  "corrections": [{"original": "mot erroné", "corrected": "correction", "note": "optionnel"}],
  "confidence": "high|medium|low"
}"""

# ---------------------------------------------------------------------------
# Étape 2 — Résumé pastoral (sur texte corrigé uniquement)
# ---------------------------------------------------------------------------

SUMMARIZE_FORBIDDEN = (
    "INTERDIT ABSOLU : corrected_transcript, corrections, recopie du texte source, "
    "ou tout champ contenant la transcription intégrale."
)

SUMMARIZE_SYSTEM_PROMPT = f"""Tu es un pasteur senior congolais, docteur en théologie.

TÂCHE UNIQUE : synthèse pastorale (message central, résumé, points clés, thèmes, références).
Tu analyses un EXTRAIT de transcription ASR — tu ne corriges PAS et ne recopies PAS le texte source.
{SUMMARIZE_FORBIDDEN}

Règles :
1. FIDÉLITÉ : uniquement le texte fourni. Pas de verset inventé.
2. central_message : max 25 mots.
3. summary : 2–3 paragraphes, max 700 mots, ton pastoral.
4. key_points : 3–6 phrases courtes. main_themes : 2–5 libellés courts.
5. key_verses / references : uniquement ce qui est explicitement dans l'extrait.

JSON valide uniquement (échappe \\n dans les chaînes)."""

SUMMARIZE_JSON_HINT = """{
  "central_message": "...",
  "summary": "...",
  "key_points": ["..."],
  "main_themes": ["..."],
  "key_verses": ["..."],
  "references": ["..."]
}"""

SUMMARIZE_ALLOWED_KEYS = (
    "central_message, summary, key_points, main_themes, key_verses, references"
)

SUMMARIZE_SINGLE_JSON_SYSTEM = f"""{SUMMARIZE_SYSTEM_PROMPT}

Clés JSON AUTORISÉES (uniquement) : {SUMMARIZE_ALLOWED_KEYS}.
Toute autre clé (corrected_transcript, corrections, confidence, etc.) est interdite."""

SUMMARIZE_META_SYSTEM = f"""Tu es un pasteur senior. Synthèse STRUCTURÉE d'un extrait de prédication.
{SUMMARIZE_FORBIDDEN}
Ne produis PAS le champ summary (il sera fait séparément).
JSON compact uniquement. Clés autorisées : central_message, key_points, main_themes, key_verses, references."""

SUMMARIZE_META_JSON_HINT = """{
  "central_message": "max 25 mots",
  "key_points": ["3 à 6 items courts"],
  "main_themes": ["2 à 5"],
  "key_verses": [],
  "references": []
}"""

SUMMARIZE_BODY_PLAIN_SYSTEM = f"""Tu es un pasteur senior congolais.
Rédige UNIQUEMENT le résumé pastoral : 2 à 3 paragraphes, ton chaleureux, max 650 mots.
{SUMMARIZE_FORBIDDEN}
Ne recopie pas la transcription. Pas de JSON. Pas de liste à puces — prose uniquement."""

MAP_SECTION_SYSTEM = f"""Tu es un pasteur senior. Tu reçois UNE section d'une longue prédication (FR/lingala).
Produis une mini-synthèse JSON compacte de cette section uniquement.
{SUMMARIZE_FORBIDDEN}"""

MAP_SECTION_JSON_HINT = """{
  "section_index": 1,
  "central_message": "idée principale de cette section",
  "key_points": ["phrases courtes"],
  "main_themes": ["thèmes"],
  "key_verses": [],
  "references": []
}"""

MAP_FINAL_META_SYSTEM = f"""Tu fusionnes plusieurs mini-synthèses de sections d'une même prédication.
Produis UN objet JSON global (message central de tout le sermon, points clés fusionnés, thèmes, versets).
{SUMMARIZE_FORBIDDEN}
Déduplique les points et versets."""

MAP_FINAL_BODY_SYSTEM = f"""Tu es un pasteur senior. Tu reçois les synthèses de TOUTES les sections d'une prédication.
Rédige le résumé pastoral FINAL (2-4 paragraphes, max 800 mots) couvrant l'ensemble du message.
{SUMMARIZE_FORBIDDEN}
Prose uniquement, pas de JSON."""

WHISPER_PROMPT_HINT = (
    "Prédication chrétienne en français, parfois en lingala. "
    "Termes fréquents : Ecclésiaste, Genèse, Ésaïe, Psaumes, Romains, Corinthiens, "
    "Saint-Esprit, Nzambe, Alléluia, rédemption, sanctification, assemblée, frère, sœur."
)


class NLPProcessingError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def whisper_prompt_hint() -> str:
    return WHISPER_PROMPT_HINT


def estimate_read_time(word_count: int, words_per_minute: int = 180) -> int:
    if word_count <= 0:
        return 0
    minutes = word_count / words_per_minute
    return max(1, int(round(minutes * 60)))


def nlp_model_label(transcription_model: str) -> str:
    if settings.nlp_provider == "openai" and settings.openai_api_key.strip():
        return f"openai:{settings.openai_summary_model}+normalize"
    return f"stub:{transcription_model}"


def _empty_result(transcript: str, ai_model: str) -> Dict:
    word_count = len(transcript.split()) if transcript else 0
    return {
        "summary": "",
        "key_points": [],
        "main_themes": [],
        "key_verses": [],
        "references": [],
        "word_count": word_count,
        "estimated_read_time": estimate_read_time(word_count),
        "ai_model": ai_model,
        "nlp_metadata": None,
    }


def _process_stub(transcript: str, ai_model: str) -> Dict:
    sentences = [s.strip() for s in transcript.split(".") if s.strip()]
    summary = sentences[0] if sentences else transcript[:200]
    word_count = len(transcript.split())
    return {
        "summary": summary,
        "key_points": sentences[:5] if sentences else [],
        "main_themes": ["foi", "communauté"] if transcript else [],
        "key_verses": [],
        "references": [],
        "word_count": word_count,
        "estimated_read_time": estimate_read_time(word_count),
        "ai_model": ai_model,
        "nlp_metadata": {
            "central_message": summary[:120] if summary else "",
            "corrected_transcript": transcript,
            "corrections": [],
            "confidence": "low",
        },
    }


def _truncate(text: str) -> str:
    max_chars = settings.openai_nlp_max_transcript_chars
    if len(text) <= max_chars:
        return text
    logger.warning("transcript tronqué NLP: %s -> %s caractères", len(text), max_chars)
    return text[:max_chars] + "\n\n[… transcription tronquée …]"


def _split_into_sections(text: str, max_chars: int) -> List[str]:
    """Découpe en sections sur paragraphes, sans perdre l'ordre."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    if not paragraphs:
        return [text[:max_chars]]

    sections: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        plen = len(para) + (2 if current else 0)
        if current and current_len + plen > max_chars:
            sections.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += plen

    if current:
        sections.append("\n\n".join(current))

    # Paragraphe isolé trop long
    final: List[str] = []
    for sec in sections:
        if len(sec) <= max_chars:
            final.append(sec)
        else:
            for i in range(0, len(sec), max_chars):
                chunk = sec[i : i + max_chars]
                if chunk.strip():
                    final.append(chunk.strip())
    return final or [text[:max_chars]]


def _excerpt_for_summarize(text: str) -> str:
    """Réduit le texte envoyé au résumé sans toucher au transcript stocké."""
    text = _truncate(text.strip())
    max_in = settings.openai_nlp_summarize_max_input_chars
    if len(text) <= max_in:
        return text
    head = int(max_in * 0.78)
    tail = max(2000, max_in - head - 80)
    logger.warning(
        "nlp summarize input excerpt: %s -> head=%s tail=%s (max_input=%s)",
        len(text),
        head,
        tail,
        max_in,
    )
    return (
        text[:head]
        + "\n\n[… milieu de la prédication omis pour l'analyse …]\n\n"
        + text[-tail:]
    )


def _extract_json_object(raw: str) -> Optional[str]:
    """Tente d'extraire un objet JSON depuis une réponse bruitée."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        return s[start : end + 1]
    return None


def _looks_like_normalize_output(content: str) -> bool:
    head = (content or "")[:800].lower()
    return "corrected_transcript" in head or '"corrections"' in head


def _prose_looks_like_recopy(summary: str, source: str) -> bool:
    """Détecte une recopie quasi intégrale de l'extrait au lieu d'un résumé."""
    s = (summary or "").strip()
    src = (source or "").strip()
    if len(s) < 300 or len(src) < 300:
        return False
    probe = src[:400].lower()
    if probe and probe in s.lower() and len(s) > len(src) * 0.55:
        return True
    return False


def _summarize_json_user(excerpt: str, schema_hint: str) -> str:
    return (
        f"Schéma JSON OBLIGATOIRE — respecte exactement ces clés, aucune autre :\n"
        f"{schema_hint}\n\n"
        f"---\nExtrait de prédication (synthèse uniquement, ne pas recopier) :\n\n{excerpt}"
    )


def _get_openai_client() -> OpenAI:
    return OpenAI(
        api_key=settings.openai_api_key,
        timeout=max(120.0, float(settings.openai_nlp_timeout_s)),
        max_retries=2,
    )


def _parse_json_content(content: str) -> Dict[str, Any]:
    for candidate in (content, _extract_json_object(content) or ""):
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    raise NLPProcessingError("JSON invalide : réponse du modèle illisible ou tronquée")


def _reject_wrong_summarize_schema(data: Dict[str, Any]) -> None:
    """Le modèle confond parfois résumé et normalisation (corrected_transcript géant)."""
    if "corrected_transcript" in data:
        blob = str(data.get("corrected_transcript") or "")
        if len(blob) > 200:
            raise NLPProcessingError(
                "schéma incorrect : le modèle a recopié la transcription au lieu du résumé"
            )
    if "corrections" in data and "summary" not in data and "central_message" not in data:
        raise NLPProcessingError("schéma incorrect : corrections sans résumé")


def _validate_full_summarize(data: Dict[str, Any]) -> None:
    _reject_wrong_summarize_schema(data)
    if not (str(data.get("summary") or "").strip() or str(data.get("central_message") or "").strip()):
        raise NLPProcessingError("schéma résumé incomplet : summary ou central_message requis")


def _validate_meta_summarize(data: Dict[str, Any]) -> None:
    _reject_wrong_summarize_schema(data)
    if str(data.get("summary") or "").strip():
        raise NLPProcessingError("schéma meta : le champ summary est interdit ici")
    if not str(data.get("central_message") or "").strip():
        raise NLPProcessingError("schéma meta : central_message requis")


def _validate_body_summarize(data: Dict[str, Any]) -> None:
    _reject_wrong_summarize_schema(data)
    summary = str(data.get("summary") or "").strip()
    if not summary:
        raise NLPProcessingError("schéma body : summary requis")
    if len(summary) > 12_000:
        raise NLPProcessingError("schéma body : summary trop long")


def _openai_json_call(
    system: str,
    user: str,
    max_tokens: int = 4096,
    validator: Optional[Callable[[Dict[str, Any]], None]] = None,
    max_attempts: Optional[int] = None,
    purpose: JsonCallPurpose = "summarize",
) -> Dict[str, Any]:
    if not settings.openai_api_key.strip():
        raise NLPProcessingError("OPENAI_API_KEY manquante pour le NLP.")

    client = _get_openai_client()
    model = settings.openai_summary_model
    attempts = max(1, max_attempts if max_attempts is not None else settings.openai_nlp_json_retry_attempts)

    for attempt in range(1, attempts + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.1 if purpose == "summarize" else 0.2,
                max_tokens=max_tokens,
            )
        except RateLimitError as e:
            raise NLPProcessingError(
                "Quota OpenAI dépassé. Vérifie ta facturation sur platform.openai.com"
            ) from e
        except (APIConnectionError, APITimeoutError) as e:
            raise NLPProcessingError(f"Connexion OpenAI impossible : {e}") from e
        except APIStatusError as e:
            raise NLPProcessingError(f"Erreur API OpenAI ({e.status_code}): {e.message}") from e

        choice = response.choices[0]
        content = choice.message.content or ""
        finish = getattr(choice, "finish_reason", None)
        if not content:
            raise NLPProcessingError("Réponse OpenAI vide")

        if finish == "length":
            logger.warning(
                "nlp openai finish_reason=length max_tokens=%s content_len=%s",
                max_tokens,
                len(content),
            )

        # Étape normalisation : corrected_transcript est le schéma attendu
        if purpose == "summarize" and _looks_like_normalize_output(content):
            logger.warning(
                "nlp summarize got normalize-shaped JSON, fallback preview=%r",
                content[:160],
            )
            raise NLPProcessingError(
                "Réponse de normalisation au lieu du résumé — repli automatique."
            )

        data = _parse_json_content(content)
        if validator:
            validator(data)
        return data

    raise NLPProcessingError("JSON invalide")


def _openai_prose_call(
    system: str,
    user: str,
    max_tokens: int,
    *,
    source_excerpt: str = "",
) -> str:
    """Résumé en texte libre — 1 seul appel (repli rare, pas de retry token)."""
    if not settings.openai_api_key.strip():
        raise NLPProcessingError("OPENAI_API_KEY manquante pour le NLP.")

    client = _get_openai_client()
    response = client.chat.completions.create(
        model=settings.openai_summary_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise NLPProcessingError("Résumé vide")
    if _looks_like_normalize_output(content) or _prose_looks_like_recopy(content, source_excerpt):
        raise NLPProcessingError("Le modèle a recopié la transcription au lieu de résumer")
    if getattr(response.choices[0], "finish_reason", None) == "length":
        logger.warning("nlp prose finish_reason=length content_len=%s", len(content))
    return content


def _as_str_list(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise NLPProcessingError(f"Champ {field} doit être une liste")
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_transcript(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    if len(text) > settings.openai_nlp_skip_full_normalize_chars:
        logger.warning(
            "nlp normalize skipped (transcript too long) len=%s threshold=%s",
            len(text),
            settings.openai_nlp_skip_full_normalize_chars,
        )
        return {
            "corrected_transcript": "",
            "corrections": [],
            "confidence": "medium",
            "normalize_skipped": True,
            "normalize_skip_reason": "transcript_too_long",
        }

    text = _truncate(text)
    try:
        data = _openai_json_call(
            NORMALIZE_SYSTEM_PROMPT,
            f"Schéma JSON :\n{NORMALIZE_JSON_HINT}\n\nTranscription ASR :\n\n{text}",
            max_tokens=min(8192, settings.openai_nlp_normalize_max_tokens),
            purpose="normalize",
        )
    except NLPProcessingError as e:
        logger.warning("nlp normalize failed, using raw transcript: %s", e.message)
        return {
            "corrected_transcript": "",
            "corrections": [],
            "confidence": "low",
            "normalize_skipped": True,
            "normalize_skip_reason": "normalize_call_failed",
        }

    corrected = (data.get("corrected_transcript") or raw).strip()
    corrections_raw = data.get("corrections") or []
    corrections: List[Dict[str, str]] = []
    if isinstance(corrections_raw, list):
        for item in corrections_raw[:20]:
            if isinstance(item, dict):
                corrections.append({
                    "original": str(item.get("original", "")).strip(),
                    "corrected": str(item.get("corrected", "")).strip(),
                    "note": str(item.get("note", "")).strip(),
                })

    confidence = str(data.get("confidence") or "medium").lower()
    if confidence not in ("high", "medium", "low"):
        confidence = "medium"

    logger.info(
        "nlp normalize ok corrected_len=%s corrections=%s confidence=%s",
        len(corrected),
        len(corrections),
        confidence,
    )
    return {
        "corrected_transcript": corrected or raw,
        "corrections": corrections,
        "confidence": confidence,
        "normalize_skipped": False,
    }


def _summarize_result_from_data(data: Dict[str, Any]) -> Dict[str, Any]:
    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise NLPProcessingError("Champ summary doit être une chaîne")
    return {
        "central_message": str(data.get("central_message") or "").strip(),
        "summary": (summary or "").strip() if isinstance(summary, str) else "",
        "key_points": _as_str_list(data.get("key_points"), "key_points")[:7],
        "main_themes": _as_str_list(data.get("main_themes"), "main_themes")[:5],
        "key_verses": _as_str_list(data.get("key_verses"), "key_verses"),
        "references": _as_str_list(data.get("references"), "references"),
    }


def _summarize_safe_pipeline(text: str) -> Dict[str, Any]:
    """
    Prédications courtes (< map-reduce) :
    1) Un seul appel JSON strict (résumé complet) — chemin nominal, 1× tokens.
    2) Si échec schéma uniquement : un seul appel prose (repli, pas de 2ᵉ JSON).
    Jamais meta JSON + prose systématiquement (évite double consommation).
    """
    excerpt = _excerpt_for_summarize(text)
    logger.info(
        "nlp summarize safe-pipeline transcript_len=%s excerpt_len=%s",
        len(text),
        len(excerpt),
    )

    try:
        data = _openai_json_call(
            SUMMARIZE_SINGLE_JSON_SYSTEM,
            _summarize_json_user(excerpt, SUMMARIZE_JSON_HINT),
            max_tokens=min(settings.openai_nlp_summarize_max_tokens, 3500),
            validator=_validate_full_summarize,
            max_attempts=1,
            purpose="summarize",
        )
        result = _summarize_result_from_data(data)
        logger.info(
            "nlp summarize single-json ok central=%r summary_len=%s key_points=%s",
            (result["central_message"] or "")[:60],
            len(result["summary"]),
            len(result["key_points"]),
        )
        result["_pipeline_mode"] = "single-json"
        return result
    except NLPProcessingError as e:
        logger.warning("nlp single-json failed, one-shot prose fallback: %s", e.message)

    summary_text = _openai_prose_call(
        SUMMARIZE_BODY_PLAIN_SYSTEM,
        f"Extrait de prédication :\n\n{excerpt}\n\nRédige le résumé pastoral.",
        max_tokens=settings.openai_nlp_summarize_body_max_tokens,
        source_excerpt=excerpt,
    )

    result = _summarize_result_from_data({
        "central_message": "",
        "summary": summary_text,
        "key_points": [],
        "main_themes": [],
        "key_verses": [],
        "references": [],
    })
    if result["summary"]:
        first = result["summary"].split(".")[0].strip()
        result["central_message"] = (first[:120] + "…") if len(first) > 120 else first
    logger.info(
        "nlp summarize prose-fallback ok central=%r summary_len=%s",
        (result["central_message"] or "")[:60],
        len(result["summary"]),
    )
    result["_pipeline_mode"] = "prose-fallback"
    return result


def _summarize_map_reduce(text: str) -> Dict[str, Any]:
    """Couvre toute la transcription : mini-synthèses par section puis fusion finale."""
    sections = _split_into_sections(text, settings.openai_nlp_map_section_chars)
    logger.info(
        "nlp map-reduce start sections=%s transcript_len=%s",
        len(sections),
        len(text),
    )

    section_notes: List[Dict[str, Any]] = []
    for i, sec in enumerate(sections, start=1):
        try:
            note = _openai_json_call(
                MAP_SECTION_SYSTEM,
                f"Section {i}/{len(sections)}.\nSchéma :\n{MAP_SECTION_JSON_HINT}\n\n"
                f"Texte de la section :\n\n{sec}",
                max_tokens=settings.openai_nlp_map_section_max_tokens,
                max_attempts=1,
                purpose="summarize",
            )
        except NLPProcessingError as e:
            logger.warning("nlp map-reduce section %s failed: %s", i, e.message)
            note = {
                "section_index": i,
                "central_message": "",
                "key_points": [],
                "main_themes": [],
                "key_verses": [],
                "references": [],
            }
        else:
            note["section_index"] = i
        section_notes.append(note)

    digest_parts: List[str] = []
    for note in section_notes:
        idx = note.get("section_index", "?")
        kps = _as_str_list(note.get("key_points"), "key_points")[:6]
        themes = _as_str_list(note.get("main_themes"), "main_themes")[:4]
        verses = _as_str_list(note.get("key_verses"), "key_verses")
        refs = _as_str_list(note.get("references"), "references")
        digest_parts.append(
            f"### Section {idx}\n"
            f"Message section : {note.get('central_message', '')}\n"
            f"Points : {'; '.join(kps)}\n"
            f"Thèmes : {'; '.join(themes)}\n"
            f"Versets : {'; '.join(verses)}\n"
            f"Références : {'; '.join(refs)}"
        )
    digest = "\n\n".join(digest_parts)

    try:
        meta = _openai_json_call(
            MAP_FINAL_META_SYSTEM,
            f"Schéma global :\n{SUMMARIZE_META_JSON_HINT}\n\nSynthèses par section :\n\n{digest}",
            max_tokens=settings.openai_nlp_summarize_meta_max_tokens,
            validator=_validate_meta_summarize,
            max_attempts=1,
        )
    except NLPProcessingError as e:
        logger.warning("nlp map-reduce meta fusion failed: %s", e.message)
        meta = {
            "central_message": str(section_notes[0].get("central_message") or ""),
            "key_points": [],
            "main_themes": [],
            "key_verses": [],
            "references": [],
        }
        for note in section_notes:
            meta["key_points"].extend(_as_str_list(note.get("key_points"), "key_points"))
            meta["main_themes"].extend(_as_str_list(note.get("main_themes"), "main_themes"))
            meta["key_verses"].extend(_as_str_list(note.get("key_verses"), "key_verses"))
            meta["references"].extend(_as_str_list(note.get("references"), "references"))
        meta["key_points"] = list(dict.fromkeys(meta["key_points"]))[:7]
        meta["main_themes"] = list(dict.fromkeys(meta["main_themes"]))[:5]
        meta["key_verses"] = list(dict.fromkeys(meta["key_verses"]))
        meta["references"] = list(dict.fromkeys(meta["references"]))

    summary_text = _openai_prose_call(
        MAP_FINAL_BODY_SYSTEM,
        f"La prédication a été analysée en {len(sections)} sections. "
        f"Synthèses détaillées :\n\n{digest}\n\nRédige le résumé pastoral final.",
        max_tokens=settings.openai_nlp_map_final_max_tokens,
        source_excerpt=text[: settings.openai_nlp_summarize_max_input_chars],
    )

    merged = {**meta, "summary": summary_text}
    result = _summarize_result_from_data(merged)
    if not result["central_message"] and result["summary"]:
        first = result["summary"].split(".")[0].strip()
        result["central_message"] = (first[:120] + "…") if len(first) > 120 else first

    logger.info(
        "nlp map-reduce done sections=%s summary_len=%s key_points=%s",
        len(sections),
        len(result["summary"]),
        len(result["key_points"]),
    )
    return result


def _summarize_corrected(corrected: str) -> Dict[str, Any]:
    text = corrected.strip()
    if len(text) >= settings.openai_nlp_map_reduce_min_chars:
        return _summarize_map_reduce(text)
    return _summarize_safe_pipeline(text)


def _process_openai_two_step(transcript: str, transcription_model: str) -> Dict:
    # Étape 1 — normalisation (échec non bloquant : on résume le transcript brut)
    normalized = _normalize_transcript(transcript)
    corrected = normalized.get("corrected_transcript") or ""
    summarize_source = corrected.strip() if corrected.strip() else transcript

    # Étape 2 — résumé (1 passage ; pas de 2ᵉ pipeline sur transcript brut)
    summary_data = _summarize_corrected(summarize_source)
    pipeline_mode = summary_data.pop("_pipeline_mode", "2-step-safe")

    word_count = len(transcript.split())
    label = nlp_model_label(transcription_model)

    nlp_metadata = {
        "central_message": summary_data["central_message"],
        "corrected_transcript": corrected if corrected.strip() else None,
        "corrections": normalized["corrections"],
        "confidence": normalized["confidence"],
        "pipeline": "map-reduce"
        if len(summarize_source.strip()) >= settings.openai_nlp_map_reduce_min_chars
        else pipeline_mode,
        "normalize_skipped": normalized.get("normalize_skipped", False),
        "map_reduce_sections": len(
            _split_into_sections(
                summarize_source.strip(),
                settings.openai_nlp_map_section_chars,
            )
        )
        if len(summarize_source.strip()) >= settings.openai_nlp_map_reduce_min_chars
        else None,
    }

    logger.info(
        "nlp 2-step ok central=%r summary_len=%s key_points=%s",
        summary_data["central_message"][:80],
        len(summary_data["summary"]),
        len(summary_data["key_points"]),
    )

    return {
        "summary": summary_data["summary"],
        "key_points": summary_data["key_points"],
        "main_themes": summary_data["main_themes"],
        "key_verses": summary_data["key_verses"],
        "references": summary_data["references"],
        "word_count": word_count,
        "estimated_read_time": estimate_read_time(word_count),
        "ai_model": label,
        "nlp_metadata": nlp_metadata,
    }


def process_transcript(transcript: str, ai_model: str) -> Dict:
    if not transcript or not transcript.strip():
        return _empty_result(transcript or "", nlp_model_label(ai_model))

    use_openai = settings.nlp_provider == "openai" and bool(settings.openai_api_key.strip())

    if use_openai:
        return _process_openai_two_step(transcript, ai_model)

    if settings.nlp_provider == "openai" and not settings.openai_api_key.strip():
        logger.warning("NLP_PROVIDER=openai mais OPENAI_API_KEY absente — repli stub")

    result = _process_stub(transcript, ai_model)
    result["ai_model"] = nlp_model_label(ai_model)
    return result
