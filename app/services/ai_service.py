from pathlib import Path
from typing import Any, Dict

from app.models import Sermon


def _load_audio_stub(file_path: Path) -> str:
    # Placeholder that pretends to transcribe audio content.
    return f"Transcript generated for {file_path.name}."


def transcribe_audio(file_path: Path) -> Dict[str, Any]:
    transcript = _load_audio_stub(file_path)
    words = transcript.split()
    return {
        "transcript": transcript,
        "transcript_words": [{"word": w, "index": i} for i, w in enumerate(words)],
        "word_count": len(words),
        "audio_duration": None,
    }


def get_audio_path_from_sermon(storage_base: Path, sermon: Sermon) -> Path | None:
    if not sermon.audio_url:
        return None
    relative = sermon.audio_url.replace("/files/", "")
    return storage_base / relative
