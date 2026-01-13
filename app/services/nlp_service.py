from typing import Dict, List, Optional


def estimate_read_time(word_count: int, words_per_minute: int = 180) -> int:
    if word_count <= 0:
        return 0
    minutes = word_count / words_per_minute
    return max(1, int(round(minutes * 60)))  # seconds


def process_transcript(transcript: str, ai_model: str) -> Dict:
    sentences = [s.strip() for s in transcript.split(".") if s.strip()]
    summary = sentences[0] if sentences else transcript[:200]
    key_points: List[str] = sentences[:5] if sentences else []
    main_themes: List[str] = ["faith", "community"] if transcript else []
    key_verses: List[str] = []
    references: List[str] = []
    word_count = len(transcript.split())
    return {
        "summary": summary,
        "key_points": key_points,
        "main_themes": main_themes,
        "key_verses": key_verses,
        "references": references,
        "word_count": word_count,
        "estimated_read_time": estimate_read_time(word_count),
        "ai_model": ai_model,
    }
