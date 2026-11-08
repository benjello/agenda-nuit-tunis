"""Range chaque événement dans une ville d'après son lieu et son adresse (voir _data/villes.yml).

Par défaut « tunis » : la plupart de nos sources sont dans le Grand Tunis.
"""
from __future__ import annotations

import re
import unicodedata

# Le premier motif qui correspond gagne. Écrits sans accents (le texte est normalisé).
_VILLES = [
    ("sousse", r"sousse|port el kantaoui|hammam sousse|msaken|akouda"),
    ("sfax", r"sfax|sakiet ezzit|kerkennah|mahres|agareb"),
    ("monastir", r"monastir|mahdia|ksar hellal|moknine|skanes|el jem|ksour essef|chebba"),
    ("nabeul", r"nabeul|hammamet|kelibia|korba|menzel temime|yasmine|cap bon|grombalia|dar chaabane"),
    ("bizerte", r"bizerte|menzel bourguiba|ras jebel"),
    ("kairouan", r"kairouan|raqqada"),
    ("sud", r"djerba|houmt souk|midoun|zarzis|gabes|medenine|tataouine|tozeur|nefta|douz|kebili|matmata|gafsa|"
            r"ben guerdane|chenini|tamerza|chebika|mides|el hamma|mareth|ghomrassen|metlaoui|redeyef|ksar ghilane|guellala|erriadh|ksar el f[ae]rch|ksar ouled soltane|ksar hadada|beni khedache|bir lahmar|remada"),
    ("autres", r"\b(?:beja|jendouba|tabarka|le kef|kef|siliana|zaghouan|kasserine|sidi bouzid|dougga|ain draham|sbeitla|testour|thala|makthar|haidra|teboursouk|bulla regia|el kef)\b"),
]


def _norme(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()


def ville(*textes: str) -> str:
    t = _norme(" ".join(x for x in textes if x))
    for v, motif in _VILLES:
        if re.search(motif, t):
            return v
    return "tunis"


def mention(texte: str) -> tuple[str, str] | None:
    """(ville, nom écrit) d'une ville hors du Grand Tunis citée dans un texte : « Direction Gabès ! » → (sud, Gabès)."""
    brut = texte or ""
    t = _norme(brut)
    for v, motif in _VILLES:
        m = re.search(motif, t)
        if m:
            # même position dans le texte d'origine (la normalisation garde la longueur des lettres latines)
            mot = brut[m.start():m.end()] if _norme(brut[m.start():m.end()]) == m.group(0) else m.group(0)
            return v, mot[:1].upper() + mot[1:]
    return None
