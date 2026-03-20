import time
from pathlib import Path
from typing import Any, Dict

import google.generativeai as genai

from app.core.config import settings
from app.models import Sermon

genai.configure(api_key=settings.gemini_api_key)

TRANSCRIPTION_PROMPT = (
    "Transcribe the following audio exactly as spoken. "
    "Return only the transcription text, without any commentary, "
    "introduction, or formatting. If the audio is silent or inaudible, return an empty string."
)


def transcribe_audio(file_path: Path) -> Dict[str, Any]:
    start = time.time()

    uploaded = genai.upload_file(str(file_path))

    model = genai.GenerativeModel("gemini-2.0-flash")
    response = model.generate_content([uploaded, TRANSCRIPTION_PROMPT])

    try:
        genai.delete_file(uploaded.name)
    except Exception:
        pass

    transcript = response.text.strip() if response.text else ""
    words = transcript.split()
    processing_time = int(time.time() - start)

    return {
        "transcript": transcript,
        "transcript_words": [{"word": w, "index": i} for i, w in enumerate(words)],
        "word_count": len(words),
        "processing_time": processing_time,
        "audio_duration": None,
    }


def get_audio_path_from_sermon(storage_base: Path, sermon: Sermon) -> Path | None:
    if not sermon.audio_url:
        return None
    relative = sermon.audio_url.replace("/files/", "")
    return storage_base / relative
