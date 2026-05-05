import json
import logging
import mimetypes
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import google.generativeai as genai
from google.api_core import exceptions as google_api_exceptions
from googleapiclient.errors import HttpError
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.core.config import settings
from app.models import Sermon

logger = logging.getLogger(__name__)

_whisper_model_lock = threading.Lock()
_whisper_model: Any = None

# Extensions souvent mal devinies par mimetypes
_AUDIO_MIME_FALLBACK: dict[str, str] = {
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".wav": "audio/wav",
    ".mp4": "audio/mp4",
}

TRANSCRIPTION_PROMPT = (
    "Transcribe the following audio exactly as spoken. "
    "Return only the transcription text, without any commentary, "
    "introduction, or formatting. If the audio is silent or inaudible, return an empty string."
)


class TranscriptionError(Exception):
    """Erreur explicite pour l'appelant HTTP (clé manquante, API, fichier Google, etc.)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def transcription_model_label() -> str:
    """Libellé stocké dans SermonOutput.ai_model selon le fournisseur actif."""
    if settings.transcription_provider == "openai":
        return f"openai:{settings.openai_transcription_model}"
    if settings.transcription_provider == "local":
        return f"local:faster-whisper:{settings.local_whisper_model_size}"
    return f"gemini:{settings.default_ai_model}"


def _mime_for_path(file_path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(file_path))
    if guessed and guessed.startswith("audio/"):
        return guessed
    ext = file_path.suffix.lower()
    if ext in _AUDIO_MIME_FALLBACK:
        return _AUDIO_MIME_FALLBACK[ext]
    return "audio/mpeg"


def _file_state_name(f: Any) -> str:
    state = f.state
    if hasattr(state, "name"):
        return str(state.name)
    return str(state)


def _wait_until_file_ready(uploaded: Any, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    f = uploaded
    while time.time() < deadline:
        st = _file_state_name(f)
        if st == "ACTIVE":
            return
        if st == "FAILED":
            err = getattr(f, "error", None)
            detail = str(err) if err else "unknown error"
            raise TranscriptionError(f"Échec du traitement du fichier sur Google: {detail}")
        time.sleep(1.0)
        f = genai.get_file(f.name)
    raise TranscriptionError("Délai dépassé en attendant le fichier audio côté Google (ACTIVE).")


def _http_error_message(e: HttpError) -> str:
    """Message API sans URL (évite de logger la clé dans les query params)."""
    if e.content:
        try:
            data = json.loads(e.content.decode())
            err = data.get("error") or {}
            if isinstance(err.get("message"), str):
                return err["message"]
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
    return e.reason or "Erreur API Google"


def _transcription_error_from_resource_exhausted(e: google_api_exceptions.ResourceExhausted) -> TranscriptionError:
    return TranscriptionError(
        "Quota ou débit Google Gemini dépassé pour ce modèle (souvent la limite gratuite). "
        "Tu peux attendre ~1 minute et réessayer, définir DEFAULT_AI_MODEL dans .env vers un autre modèle "
        "disponible pour ta clé, ou activer la facturation sur le projet Google lié à la clé. "
        "Voir https://ai.google.dev/gemini-api/docs/rate-limits et https://ai.dev/rate-limit ."
    )


def _transcription_error_from_http(e: HttpError) -> TranscriptionError:
    msg = _http_error_message(e)
    if "API key" in msg or "API_KEY" in msg:
        return TranscriptionError(
            "Clé API Google Gemini invalide ou expirée. Crée une nouvelle clé sur "
            "https://aistudio.google.com/apikey puis mets à jour GEMINI_API_KEY dans .env et redémarre le serveur."
        )
    return TranscriptionError(f"Erreur Google Generative Language: {msg}")


def _text_from_response(response: Any) -> str:
    try:
        if response.text:
            return response.text.strip()
    except ValueError:
        pass
    if not response.candidates:
        return ""
    parts = response.candidates[0].content.parts
    return "".join(getattr(p, "text", "") or "" for p in parts).strip()


def _build_result(transcript: str, start: float) -> Dict[str, Any]:
    words = transcript.split()
    wall_s = int(time.time() - start)
    return {
        "transcript": transcript,
        "transcript_words": [{"word": w, "index": i} for i, w in enumerate(words)],
        "word_count": len(words),
        "processing_time": wall_s,
        "audio_duration": None,
    }


def _transcribe_gemini(file_path: Path) -> Dict[str, Any]:
    if not settings.gemini_api_key or not settings.gemini_api_key.strip():
        raise TranscriptionError(
            "GEMINI_API_KEY manquante. Ajoute-la dans le fichier .env (Google AI Studio), "
            "ou utilise TRANSCRIPTION_PROVIDER=openai (OPENAI_API_KEY) ou local (faster-whisper)."
        )

    genai.configure(api_key=settings.gemini_api_key)
    start = time.time()
    mime = _mime_for_path(file_path)
    try:
        uploaded = genai.upload_file(str(file_path), mime_type=mime)
    except HttpError as e:
        logger.warning("upload_file Gemini: %s", _http_error_message(e))
        raise _transcription_error_from_http(e) from None
    except google_api_exceptions.ResourceExhausted as e:
        logger.warning("upload_file Gemini quota: %s", str(e)[:300])
        raise _transcription_error_from_resource_exhausted(e) from None
    except Exception as e:
        logger.exception("upload_file Gemini")
        raise TranscriptionError(f"Impossible d'envoyer l'audio à Google: {e!s}") from e

    try:
        _wait_until_file_ready(uploaded, timeout_s=settings.gemini_file_ready_timeout_s)

        model = genai.GenerativeModel(settings.default_ai_model)
        response = model.generate_content([uploaded, TRANSCRIPTION_PROMPT])

        transcript = _text_from_response(response)
    except TranscriptionError:
        raise
    except HttpError as e:
        logger.warning("generate_content transcription: %s", _http_error_message(e))
        raise _transcription_error_from_http(e) from None
    except google_api_exceptions.ResourceExhausted as e:
        logger.warning("generate_content transcription quota: %s", str(e)[:300])
        raise _transcription_error_from_resource_exhausted(e) from None
    except Exception as e:
        logger.exception("generate_content transcription")
        raise TranscriptionError(f"Échec de la transcription Gemini: {e!s}") from e
    finally:
        try:
            genai.delete_file(uploaded.name)
        except Exception:
            logger.debug("delete_file %s (ignored)", uploaded.name, exc_info=True)

    return _build_result(transcript, start)


def _transcribe_openai(file_path: Path) -> Dict[str, Any]:
    if not settings.openai_api_key or not settings.openai_api_key.strip():
        raise TranscriptionError(
            "OPENAI_API_KEY manquante. Ajoute-la dans .env pour TRANSCRIPTION_PROVIDER=openai, "
            "ou utilise gemini / local selon ta configuration."
        )

    start = time.time()
    client = OpenAI(api_key=settings.openai_api_key)
    try:
        with open(file_path, "rb") as audio_f:
            tr = client.audio.transcriptions.create(
                model=settings.openai_transcription_model,
                file=(file_path.name, audio_f, _mime_for_path(file_path)),
            )
    except RateLimitError as e:
        logger.warning("OpenAI transcription rate limit: %s", str(e)[:300])
        raise TranscriptionError(
            "Limite de débit ou quota OpenAI atteint. Réessaie plus tard ou vérifie ton forfait / facturation "
            "sur https://platform.openai.com/"
        ) from None
    except APIStatusError as e:
        logger.warning("OpenAI transcription API: %s", str(e.message)[:300] if e.message else "")
        raise TranscriptionError(f"Erreur API OpenAI (transcription): {e.message}") from None
    except (APIConnectionError, APITimeoutError) as e:
        logger.warning("OpenAI transcription réseau: %s", str(e)[:300])
        raise TranscriptionError(f"Réseau OpenAI indisponible ou délai dépassé: {e!s}") from None
    except Exception as e:
        logger.exception("OpenAI transcription")
        raise TranscriptionError(f"Échec de la transcription OpenAI: {e!s}") from e

    transcript = (getattr(tr, "text", None) or "").strip()
    return _build_result(transcript, start)


def _resolve_local_whisper_device_compute() -> tuple[str, str]:
    """Choix device / precision pour faster-whisper."""
    raw_ct = settings.local_whisper_compute_type.strip()
    mode = settings.local_whisper_device.strip().lower()
    if mode == "cuda":
        return "cuda", raw_ct or "float16"
    if mode == "cpu":
        return "cpu", raw_ct or "int8"
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", raw_ct or "float16"
    except Exception:
        logger.debug("CUDA check for faster-whisper (ignored)", exc_info=True)
    return "cpu", raw_ct or "int8"


def _get_local_whisper_model():
    global _whisper_model
    with _whisper_model_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            device, compute_type = _resolve_local_whisper_device_compute()
            download_root: Optional[str] = (
                settings.local_whisper_download_root.strip() or None
            )
            logger.info(
                "Chargement faster-whisper modèle=%s device=%s compute_type=%s",
                settings.local_whisper_model_size,
                device,
                compute_type,
            )
            _whisper_model = WhisperModel(
                settings.local_whisper_model_size,
                device=device,
                compute_type=compute_type,
                download_root=download_root,
            )
        return _whisper_model


def _transcribe_local(file_path: Path) -> Dict[str, Any]:
    start = time.time()
    try:
        model = _get_local_whisper_model()
    except Exception as e:
        logger.exception("chargement faster-whisper")
        raise TranscriptionError(
            "Impossible de charger faster-whisper. Installe les deps (pip install faster-whisper), "
            "ffmpeg sur le système, et vérifie LOCAL_WHISPER_MODEL_SIZE."
        ) from e

    transcribe_kw: Dict[str, Any] = {"beam_size": 5, "vad_filter": True}
    lang = settings.local_whisper_language.strip()
    if lang:
        transcribe_kw["language"] = lang

    try:
        segments, info = model.transcribe(str(file_path), **transcribe_kw)
        transcript = "".join(seg.text for seg in segments).strip()
    except Exception as e:
        logger.exception("transcription locale faster-whisper")
        raise TranscriptionError(f"Échec transcription locale: {e!s}") from e

    out = _build_result(transcript, start)
    dur = getattr(info, "duration", None)
    if dur is not None:
        try:
            out["audio_duration"] = int(float(dur))
        except (TypeError, ValueError):
            pass
    return out


def transcribe_audio(file_path: Path) -> Dict[str, Any]:
    if not file_path.is_file():
        raise TranscriptionError(f"Fichier audio introuvable: {file_path}")

    logger.info(
        "transcribe_audio file=%s provider=%s model=%s",
        file_path.name,
        settings.transcription_provider,
        settings.openai_transcription_model
        if settings.transcription_provider == "openai"
        else (
            settings.local_whisper_model_size
            if settings.transcription_provider == "local"
            else settings.default_ai_model
        ),
    )

    if settings.transcription_provider == "openai":
        return _transcribe_openai(file_path)
    if settings.transcription_provider == "local":
        return _transcribe_local(file_path)
    return _transcribe_gemini(file_path)


def get_audio_path_from_sermon(storage_base: Path, sermon: Sermon) -> Path | None:
    if not sermon.audio_url:
        return None
    relative = sermon.audio_url.replace("/files/", "")
    return storage_base / relative
