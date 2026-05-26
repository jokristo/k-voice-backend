import json
import logging
from typing import Any, Dict, List

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

SUMMARIZE_SYSTEM_PROMPT = """Tu es un pasteur senior congolais, docteur en théologie, habitué aux prédications francophones avec insertions en lingala.

Tu reçois la transcription CORRIGÉE d'une prédication. Produis une analyse fidèle et percutante.

Règles strictes :
1. FIDÉLITÉ : base-toi UNIQUEMENT sur le texte fourni. N'invente aucun verset.
2. Si un livre biblique est mentionné sans verset précis, ne cite PAS un verset « classique » de ce livre par habitude.
3. key_verses : uniquement les références explicitement citées ou indiscutables dans le texte.
4. central_message : une phrase percutante (max 25 mots) capturant le cœur du message.
5. summary : 2 à 3 paragraphes clairs, ton pastoral, application concrète pour l'assemblée.
6. key_points : 3 à 6 points, phrases complètes, actionnables.
7. main_themes : 2 à 5 thèmes (expressions courtes).
8. references : toutes les références bibliques mentionnées (livres ou versets).
9. Respecte le mélange FR/lingala si le prédicateur l'utilise ; glosser le lingala si nécessaire dans le résumé.

Réponds UNIQUEMENT en JSON valide."""

SUMMARIZE_JSON_HINT = """{
  "central_message": "phrase percutante",
  "summary": "résumé en paragraphes",
  "key_points": ["..."],
  "main_themes": ["..."],
  "key_verses": ["Jean 3:16"],
  "references": ["..."]
}"""

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


def _openai_json_call(system: str, user: str, max_tokens: int = 4096) -> Dict[str, Any]:
    if not settings.openai_api_key.strip():
        raise NLPProcessingError("OPENAI_API_KEY manquante pour le NLP.")

    client = OpenAI(api_key=settings.openai_api_key)
    model = settings.openai_summary_model

    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
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

    content = response.choices[0].message.content
    if not content:
        raise NLPProcessingError("Réponse OpenAI vide")

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise NLPProcessingError(f"JSON invalide : {e}") from e

    if not isinstance(data, dict):
        raise NLPProcessingError("Objet JSON attendu")
    return data


def _as_str_list(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise NLPProcessingError(f"Champ {field} doit être une liste")
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_transcript(raw: str) -> Dict[str, Any]:
    text = _truncate(raw.strip())
    data = _openai_json_call(
        NORMALIZE_SYSTEM_PROMPT,
        f"Schéma JSON :\n{NORMALIZE_JSON_HINT}\n\nTranscription ASR :\n\n{text}",
        max_tokens=min(8192, settings.openai_nlp_normalize_max_tokens),
    )

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
    }


def _summarize_corrected(corrected: str) -> Dict[str, Any]:
    text = _truncate(corrected)
    data = _openai_json_call(
        SUMMARIZE_SYSTEM_PROMPT,
        f"Schéma JSON :\n{SUMMARIZE_JSON_HINT}\n\nTranscription corrigée :\n\n{text}",
        max_tokens=min(4096, settings.openai_nlp_summarize_max_tokens),
    )

    summary = data.get("summary")
    if summary is not None and not isinstance(summary, str):
        raise NLPProcessingError("Champ summary doit être une chaîne")

    central = str(data.get("central_message") or "").strip()

    return {
        "central_message": central,
        "summary": (summary or "").strip(),
        "key_points": _as_str_list(data.get("key_points"), "key_points")[:7],
        "main_themes": _as_str_list(data.get("main_themes"), "main_themes")[:5],
        "key_verses": _as_str_list(data.get("key_verses"), "key_verses"),
        "references": _as_str_list(data.get("references"), "references"),
    }


def _process_openai_two_step(transcript: str, transcription_model: str) -> Dict:
    # Étape 1 — normalisation
    normalized = _normalize_transcript(transcript)
    corrected = normalized["corrected_transcript"]

    # Étape 2 — résumé sur texte corrigé
    summary_data = _summarize_corrected(corrected)

    word_count = len(corrected.split())
    label = nlp_model_label(transcription_model)

    nlp_metadata = {
        "central_message": summary_data["central_message"],
        "corrected_transcript": corrected,
        "corrections": normalized["corrections"],
        "confidence": normalized["confidence"],
        "pipeline": "2-step",
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
