"""
Lightweight language detection.
Supports English and Kinyarwanda (primary studio languages).
"""

import logging
import re

logger = logging.getLogger(__name__)

_KIN_PATTERNS = re.compile(
    r"\b(muraho|mwaramutse|mwiriwe|ndashimye|bite|amakuru|neza|"
    r"yego|oya|urakoze|si|ndi|nza|ntabwo|kuki|gute|iki|ibyo|kigali)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """
    Returns 'rw' for Kinyarwanda, 'en' for English.
    Fast heuristic first; falls back to langdetect for ambiguous cases.
    """
    if not text or len(text.strip()) < 3:
        return "en"

    if _KIN_PATTERNS.search(text):
        return "rw"

    try:
        from langdetect import detect

        lang = detect(text)
        return "rw" if lang in ("rw", "rn") else "en"
    except Exception:
        return "en"
