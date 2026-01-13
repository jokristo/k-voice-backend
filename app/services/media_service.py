import subprocess
from pathlib import Path
from typing import Optional


def get_audio_duration_seconds(file_path: Path) -> Optional[int]:
    """
    Returns duration in seconds using ffprobe if available, otherwise None.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        duration = float(result.stdout.strip())
        return int(duration)
    except Exception:
        return None
