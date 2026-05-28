import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class MediaProcessingError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def ffmpeg_available() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def get_audio_duration_seconds(file_path: Path) -> Optional[int]:
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
            timeout=120,
        )
        duration = float(result.stdout.strip())
        return max(1, int(round(duration)))
    except Exception:
        return None


def _bitrate_kbps_for_target(duration_s: int, target_bytes: int) -> int:
    """Bitrate (kbps) pour viser target_bytes sur toute la durée."""
    needed_kbps = int((target_bytes * 8) / (duration_s * 1000) * 0.90)
    floor = settings.audio_compression_floor_kbps
    ceiling = settings.audio_compression_max_kbps
    return max(floor, min(ceiling, needed_kbps))


def _encode_mp3(source: Path, dest: Path, bitrate_kbps: int) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                f"{bitrate_kbps}k",
                str(dest),
            ],
            capture_output=True,
            check=True,
            timeout=3600,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="replace")[-500:]
        raise MediaProcessingError(f"Échec ffmpeg : {stderr}") from e


def _try_compress_to_target(source: Path, target_bytes: int) -> Tuple[Optional[Path], int]:
    """
    Essaie plusieurs débits jusqu'à tenir dans target_bytes.
    Retourne (fichier_mp3, taille) ou (None, 0) si échec.
    """
    duration_s = get_audio_duration_seconds(source) or max(
        60, int(source.stat().st_size / (96 * 1024 / 8))
    )
    first_bitrate = _bitrate_kbps_for_target(duration_s, target_bytes)
    ladder = []
    for rate in (
        first_bitrate,
        96,
        64,
        48,
        32,
        24,
        settings.audio_compression_floor_kbps,
        16,
    ):
        if rate not in ladder and rate >= 16:
            ladder.append(rate)
    ladder.sort(reverse=True)

    out_path = source.with_name(f"{source.stem}_compressed.mp3")

    for bitrate_kbps in ladder:
        if out_path.exists():
            out_path.unlink(missing_ok=True)
        logger.info(
            "compress attempt source=%s bitrate=%sk target_mb=%.1f",
            source.name,
            bitrate_kbps,
            target_bytes / (1024 * 1024),
        )
        _encode_mp3(source, out_path, bitrate_kbps)
        out_size = out_path.stat().st_size
        if out_size <= target_bytes:
            return out_path, out_size

    if out_path.exists():
        out_path.unlink(missing_ok=True)
    return None, 0


def _extract_audio_segment(
    source: Path,
    dest: Path,
    start_s: float,
    duration_s: float,
    bitrate_kbps: int,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start_s),
                "-t",
                str(duration_s),
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                f"{bitrate_kbps}k",
                str(dest),
            ],
            capture_output=True,
            check=True,
            timeout=3600,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="replace")[-500:]
        raise MediaProcessingError(f"Échec extraction segment ffmpeg : {stderr}") from e


def _split_audio_mp3(source: Path, target_bytes: int) -> List[Path]:
    """
    Découpe en segments MP3 avec chevauchement temporel (overlap).
    Chaque segment ≤ target_bytes ; les jonctions se recouvrent pour Whisper.
    """
    floor_kbps = settings.audio_compression_floor_kbps
    overlap_s = max(10, settings.whisper_chunk_overlap_seconds)
    segment_seconds = max(
        300,
        int((target_bytes * 8) / (floor_kbps * 1000) * 0.88),
    )
    stride_s = max(120, segment_seconds - overlap_s)

    duration_s = get_audio_duration_seconds(source)
    if not duration_s or duration_s < 1:
        raise MediaProcessingError("Impossible de lire la durée audio pour le découpage.")

    chunk_dir = source.parent / f"{source.stem}_chunks"
    if chunk_dir.exists():
        for old in chunk_dir.glob("part_*.mp3"):
            old.unlink()
    chunk_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "split audio overlap source=%s duration_s=%s segment_s=%s overlap_s=%s stride_s=%s",
        source.name,
        duration_s,
        segment_seconds,
        overlap_s,
        stride_s,
    )

    parts: List[Path] = []
    start = 0.0
    index = 0
    while start < duration_s - 0.5:
        seg_len = min(float(segment_seconds), float(duration_s) - start)
        out_path = chunk_dir / f"part_{index:03d}.mp3"
        _extract_audio_segment(source, out_path, start, seg_len, floor_kbps)
        if out_path.stat().st_size > target_bytes:
            out_path.unlink(missing_ok=True)
            raise MediaProcessingError(
                f"Segment {out_path.name} > {target_bytes // (1024 * 1024)} Mo malgré la durée cible."
            )
        parts.append(out_path)
        if start + seg_len >= duration_s - 0.5:
            break
        start += stride_s
        index += 1

    if not parts:
        raise MediaProcessingError("Découpage audio : aucun segment produit")

    logger.info(
        "split overlap done parts=%s overlap_s=%s total_mb=%.1f",
        len(parts),
        overlap_s,
        sum(p.stat().st_size for p in parts) / (1024 * 1024),
    )
    return parts


def _finalize_compressed(
    source: Path,
    out_path: Path,
    out_size: int,
    *,
    original_size: Optional[int] = None,
) -> Tuple[Path, bool]:
    if out_path.resolve() == source.resolve():
        return source, False
    orig = original_size if original_size is not None else source.stat().st_size
    source.unlink(missing_ok=True)
    final_path = source.with_suffix(".mp3")
    if final_path.exists() and final_path != out_path:
        final_path.unlink(missing_ok=True)
    out_path.rename(final_path)
    logger.info(
        "compress done out=%s size=%s (was %s, ratio=%.2f)",
        final_path.name,
        out_size,
        orig,
        out_size / max(1, orig),
    )
    return final_path, True


def compress_audio_for_storage(file_path: Path) -> Tuple[Path, bool]:
    """
    Normalise en MP3 mono pour le stockage (limite max_upload_size_mb).
    Ne force pas la limite Whisper 24 Mo — cela se fait à la transcription.
    """
    if not settings.audio_compression_enabled:
        return file_path, False

    if not file_path.is_file():
        raise MediaProcessingError(f"Fichier introuvable : {file_path}")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    original_size = file_path.stat().st_size

    if original_size <= max_bytes and file_path.suffix.lower() in (".mp3", ".mpeg"):
        return file_path, False

    if not ffmpeg_available():
        if original_size > max_bytes:
            raise MediaProcessingError(
                "ffmpeg n'est pas installé. Installez-le (brew install ffmpeg) ou réduisez le fichier."
            )
        return file_path, False

    orig_size = original_size
    target_bytes = max_bytes
    duration_s = get_audio_duration_seconds(file_path) or max(
        60, int(original_size / (96 * 1024 / 8))
    )
    # Stockage : viser une bonne qualité vocale sans dépasser la limite upload
    storage_bitrate = min(
        settings.audio_compression_max_kbps,
        max(64, _bitrate_kbps_for_target(duration_s, target_bytes)),
    )

    out_path = file_path.with_name(f"{file_path.stem}_compressed.mp3")
    if out_path.exists():
        out_path.unlink()
    _encode_mp3(file_path, out_path, storage_bitrate)
    out_size = out_path.stat().st_size

    if out_size > max_bytes:
        out_path.unlink(missing_ok=True)
        compressed, out_size = _try_compress_to_target(file_path, max_bytes)
        if not compressed:
            raise MediaProcessingError(
                f"Fichier trop volumineux même après compression (>{settings.max_upload_size_mb} Mo)."
            )
        return _finalize_compressed(file_path, compressed, out_size, original_size=orig_size)

    return _finalize_compressed(file_path, out_path, out_size, original_size=orig_size)


def compress_audio_to_mp3(
    file_path: Path,
    *,
    target_max_bytes: Optional[int] = None,
) -> Tuple[Path, bool]:
    """Compresse sous target_max_bytes (défaut : cible Whisper)."""
    if not settings.audio_compression_enabled:
        return file_path, False

    if not file_path.is_file():
        raise MediaProcessingError(f"Fichier introuvable : {file_path}")

    target_bytes = target_max_bytes or (settings.audio_compression_target_mb * 1024 * 1024)
    original_size = file_path.stat().st_size

    if original_size <= target_bytes and file_path.suffix.lower() in (".mp3", ".mpeg"):
        return file_path, False

    if not ffmpeg_available():
        if original_size > target_bytes:
            raise MediaProcessingError(
                "ffmpeg n'est pas installé sur le serveur. "
                "Installez ffmpeg (brew install ffmpeg) ou compressez le fichier manuellement en MP3."
            )
        return file_path, False

    compressed, out_size = _try_compress_to_target(file_path, target_bytes)
    if compressed:
        return _finalize_compressed(file_path, compressed, out_size)

    raise MediaProcessingError(
        f"Impossible de compresser sous {target_bytes / (1024 * 1024):.0f} Mo. "
        "La prédication sera découpée automatiquement à la transcription."
    )


def prepare_whisper_audio_paths(file_path: Path) -> List[Path]:
    """
    Retourne un ou plusieurs MP3, chacun ≤ limite Whisper.
    Découpe automatiquement si la compression seule ne suffit pas.
    """
    target = settings.openai_whisper_max_file_mb * 1024 * 1024
    target_compress = settings.audio_compression_target_mb * 1024 * 1024

    if not file_path.is_file():
        raise MediaProcessingError(f"Fichier introuvable : {file_path}")

    if file_path.stat().st_size <= target:
        return [file_path]

    if not ffmpeg_available():
        raise MediaProcessingError("ffmpeg requis pour préparer l'audio pour Whisper.")

    compressed, out_size = _try_compress_to_target(file_path, target_compress)
    if compressed and out_size <= target:
        final, _ = _finalize_compressed(file_path, compressed, out_size)
        return [final]

    if compressed and compressed.exists():
        compressed.unlink(missing_ok=True)

    return _split_audio_mp3(file_path, target)


def ensure_audio_ready_for_transcription(file_path: Path) -> Path:
    """Compat : retourne le premier segment (utiliser prepare_whisper_audio_paths pour tout)."""
    paths = prepare_whisper_audio_paths(file_path)
    return paths[0]
