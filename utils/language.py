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
}

_FR_WORDS = {
    "bonjour", "bonsoir", "salut", "merci", "beaucoup", "prix", "combien",
    "forfait", "séance", "photo", "photos", "enfant", "famille", "studio",
    "domicile", "cadre", "cadres", "gâteau", "gateau", "vidéo", "video",
    "réservation", "reserver", "réserver", "tarif", "tarifs", "cher",
    "adresse", "où", "ou", "quand", "heure", "jour", "semaine",
}

# Regex pour les mots courts / patterns morphologiques RW
_KIN_PATTERN = re.compile(
    r"\b(muraho|mwaramutse|mwiriwe|ndashimye|amakuru|"
    r"yego|oya|hoya|urakoze|murakoze|ntakibazo|twayakiriye|"
    r"ndashaka|nshaka|ibiciro|amafoto|umwana|isoko|"
    r"mwuzuze|nimubwire|nyamuneka|dore|noneho|"
    r"murifuzako|twabokolera|twabongereramo|"
    r"kwishyura|naramaze|nifuza|kugira|cyane|"
    r"nziza|nibura|ariko|kandi|rwose)\b",
    re.IGNORECASE,
)

_FR_PATTERN = re.compile(
    r"\b(bonjour|bonsoir|merci|combien|forfait|séance|photo|photos|enfant|famille|"
    r"studio|domicile|cadre|gâteau|gateau|vidéo|video|réservation|réserver|"
    r"tarif|adresse|comment|pourquoi|avec|sans|est-ce|votre|notre)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """
    Returns 'rw' for Kinyarwanda, 'fr' for French, 'en' for English.

    Priority order:
      1. Empty / too short → default 'en'
      2. Kinyarwanda Regex pattern match → 'rw'
      3. French Regex pattern match → 'fr'
      4. Word-set lookup on each token
      5. Morphological hits for RW
      6. langdetect fallback
    """
    if not text or len(text.strip()) < 2:
        return "en"

    # Étape 1 — regex rapide RW
    if _KIN_PATTERN.search(text):
        return "rw"

    # Étape 2 — regex rapide FR
    if _FR_PATTERN.search(text):
        return "fr"

    # Étape 3 — lookup par token
    tokens = set(re.sub(r"[?!.,;]", "", text.lower()).split())
    if tokens & _KIN_WORDS:
        return "rw"
    if tokens & _FR_WORDS:
        return "fr"

    # Étape 4 — patterns morphologiques du Kinyarwanda
    rw_prefixes = ("nk", "mw", "rw", "bw", "tw", "cy", "ny", "by", "nz", "nd", "nt")
    rw_morpho_hits = sum(
        1 for w in tokens
        if len(w) >= 4 and any(w.startswith(p) for p in rw_prefixes)
    )
    if rw_morpho_hits >= 2:
        return "rw"

    # Étape 5 — fallback langdetect
    try:
        from langdetect import detect
        lang = detect(text)
        if lang in ("rw", "rn"):
            return "rw"
        if lang == "fr":
            return "fr"
        return "en"
    except Exception:
        return "en"