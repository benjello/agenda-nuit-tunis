"""Scraper générique : calendrier iCal (.ics), par exemple un agenda Google public.

Un lieu qui tient son programme dans Google Agenda peut le partager en public :
l'adresse « au format iCal » suffit, sans écrire de code.
"""
from __future__ import annotations

import datetime as dt
import re

from ..commun import Evenement, propre, telecharger


def _deplier(texte: str) -> list[str]:
    # Les lignes longues d'un .ics continuent sur la ligne suivante, qui commence par un espace.
    return re.sub(r"\r?\n[ \t]", "", texte).splitlines()


def _date(valeur: str) -> dt.datetime | None:
    v = valeur.strip().rstrip("Z")
    for f in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            return dt.datetime.strptime(v, f)
        except ValueError:
            continue
    return None


def _valeur(v: str) -> str:
    return propre(v.replace("\\n", " ").replace("\\,", ",").replace("\;", ";"))


def depuis_ics(texte: str, source: dict) -> list[Evenement]:
    lieu_defaut = (source.get("options") or {}).get("lieu", source["nom"])
    res, ev = [], None
    for ligne in _deplier(texte):
        if ligne == "BEGIN:VEVENT":
            ev = {}
        elif ligne == "END:VEVENT" and ev is not None:
            debut = _date(ev.get("DTSTART", ""))
            if debut and ev.get("SUMMARY"):
                fin = _date(ev.get("DTEND", ""))
                res.append(Evenement(titre=_valeur(ev["SUMMARY"]), debut=debut, fin=fin,
                                     lien=_valeur(ev.get("URL", "")) or source["url"],
                                     lieu=_valeur(ev.get("LOCATION", "")) or lieu_defaut))
            ev = None
        elif ev is not None and ":" in ligne:
            cle, valeur = ligne.split(":", 1)
            ev[cle.split(";")[0]] = valeur
    return res


def recuperer(source: dict) -> list[Evenement]:
    return depuis_ics(telecharger(source["url"]), source)
