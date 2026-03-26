"""
Lightweight language detection.
Supports English and Kinyarwanda (primary studio languages).
"""

import logging
import re

logger = logging.getLogger(__name__)

# ─── Mots fréquents dans les vraies conversations clients ───────────────────
_KIN_WORDS = {
    # Salutations
    "muraho", "mwaramutse", "mwiriwe", "murakoze", "urakoze",
    "murakoze cyane", "ntakibazo", "twayakiriye", "nziza",

    # # Réponses courantes
    # "yego", "oya", "hoya", "ndashaka", "nshaka", "ngomba",
    # "ntifuza", "sinshaka", "ntabwo", "sinjye", "anze",
    # "nzaza", "twaza", "neza",

    # # Questions / exploration
    # "ibiciro", "ibiro", "gute", "kuki", "iki", "bite",
    # "ese", "ryari", "he", "nde", "iki",

    # # Discovery & booking
    # "mu rugo", "muri studio", "isoko", "umunsi", "isaha",
    # "igitsina", "imyaka", "izina", "umwana", "abana",
    # "amafoto", "ifoto", "package", "packages",
    # "gutangwa", "igihe",

    # # Paiement
    # "kwishyura", "naramaze", "nishyuye", "ishyura",
    # "booking", "payment",

    # # Verbes / connecteurs communs
    # "ndashaka", "nifuza", "murifuzako", "twabongereramo",
    # "twabakorera", "tubakorera", "dukore", "dukorane",
    # "kugira", "ngo", "kandi", "ariko", "cyane", "rwose",
    # "nibura", "nyuma", "mbere", "hanyuma",

    # # Phrases réelles observées
    # "mwuzuze", "nimubwire", "nyamuneka", "ihitamo",
    # "naramaze", "ibyo", "uko", "hari", "niba",
    # "dore", "ubu", "maze", "noneho",
}

# Regex pour les mots courts / patterns morphologiques RW
_KIN_PATTERN = re.compile(
    r"\b(muraho|mwaramutse|mwiriwe|ndashimye|amakuru|"
    r"yego|oya|hoya|urakoze|murakoze|ntakibazo|twayakiriye|"
    r"ndashaka|nshaka|ibiciro|amafoto|umwana|isoko|"
    r"mwuzuze|nimubwire|nyamuneka|dore|noneho|"
    r"murifuzako|twabakorera|twabongereramo|"
    r"kwishyura|naramaze|nifuza|kugira|cyane|"
    r"nziza|nibura|ariko|kandi|rwose)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """
    Returns 'rw' for Kinyarwanda, 'en' for English.

    Priority order:
      1. Empty / too short → default 'en'
      2. Regex pattern match → 'rw' (fast, no import)
      3. Word-set lookup on each token → 'rw'
      4. langdetect fallback → 'rw' if rw/rn, else 'en'
    """
    if not text or len(text.strip()) < 2:
        return "en"

    # Étape 1 — regex rapide
    if _KIN_PATTERN.search(text):
        return "rw"

    # Étape 2 — lookup par token (couvre les mots hors regex)
    tokens = set(re.sub(r"[?!.,;]", "", text.lower()).split())
    if tokens & _KIN_WORDS:
        return "rw"

    # Étape 3 — patterns morphologiques du Kinyarwanda
    # Les mots RW commencent souvent par ces préfixes et font 4+ lettres
    rw_prefixes = ("nk", "mw", "rw", "bw", "tw", "cy", "ny", "by", "nz", "nd", "nt")
    rw_morpho_hits = sum(
        1 for w in tokens
        if len(w) >= 4 and any(w.startswith(p) for p in rw_prefixes)
    )
    if rw_morpho_hits >= 2:
        return "rw"

    # Étape 4 — fallback langdetect
    try:
        from langdetect import detect
        lang = detect(text)
        return "rw" if lang in ("rw", "rn") else "en"
    except Exception:
        return "en"