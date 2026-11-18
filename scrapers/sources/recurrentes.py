"""Soirées récurrentes : « chaque mercredi, Rywa Live Band au Rock'n'Rolla ».

Beaucoup de lieux de la nuit ont des rendez-vous fixes qu'ils n'annoncent qu'en story, ou la veille.
On les note une fois dans `_data/recurrentes.yml` et ce scraper crée les prochaines dates (deux semaines).

Chaque entrée garde la date de la dernière preuve (`verifie_le` : une publication, un appel au lieu).
Au-delà de `JOURS_VALIDITE` jours sans nouvelle preuve, la soirée n'est plus publiée : elle a pu s'arrêter.

Champs d'une entrée :
  titre, lieu, categorie, lien (page qui prouve le rendez-vous)
  jours      un jour (« mercredi ») ou une liste (« [vendredi, samedi] »)
  heure      « 21:00 » ; fin « 02:00 » (facultatif, le lendemain si plus tôt que l'heure de début)
  adresse, prix, description (facultatifs)
  verifie_le AAAA-MM-JJ
  sauf       liste de dates sans soirée (fermeture, ramadan…), facultatif
"""
from __future__ import annotations

import datetime as dt

import yaml

from ..commun import RACINE, Evenement

FICHIER = RACINE / "_data" / "recurrentes.yml"
JOURS = {"lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4, "samedi": 5, "dimanche": 6}
HORIZON = 14          # jours publiés à l'avance
JOURS_VALIDITE = 60   # une soirée sans preuve récente n'est plus publiée


def _heure(texte) -> tuple[int, int]:
    h, _, mn = str(texte or "00:00").replace("h", ":").partition(":")
    return int(h), int(mn or 0)


def dates(entree: dict, aujourd_hui: dt.date, horizon: int = HORIZON) -> list[dt.date]:
    jours = entree.get("jours") or []
    jours = [jours] if isinstance(jours, str) else jours
    numeros = {JOURS[j.strip().lower()] for j in jours}
    sauf = {str(d) for d in entree.get("sauf") or []}
    res = []
    for i in range(horizon):
        d = aujourd_hui + dt.timedelta(days=i)
        if d.weekday() in numeros and d.isoformat() not in sauf:
            res.append(d)
    return res


def valide(entree: dict, aujourd_hui: dt.date) -> bool:
    v = entree.get("verifie_le")
    if not v:
        return False
    v = v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))
    return (aujourd_hui - v).days <= JOURS_VALIDITE


def evenements(entrees: list[dict], aujourd_hui: dt.date | None = None) -> list[Evenement]:
    aujourd_hui = aujourd_hui or dt.date.today()
    res = []
    for x in entrees:
        if not valide(x, aujourd_hui):
            print(f"  recurrentes : « {x.get('titre')} » sans preuve depuis {JOURS_VALIDITE} jours, pas publiée")
            continue
        h, mn = _heure(x.get("heure"))
        for d in dates(x, aujourd_hui):
            debut = dt.datetime(d.year, d.month, d.day, h, mn)
            fin = None
            if x.get("fin"):
                hf, mf = _heure(x["fin"])
                fin = dt.datetime(d.year, d.month, d.day, hf, mf)
                if fin <= debut:  # « 22:00 → 04:00 » : la fin est le lendemain
                    fin += dt.timedelta(days=1)
            res.append(Evenement(
                titre=x["titre"], debut=debut, fin=fin, lien=x["lien"], lieu=x.get("lieu", ""),
                adresse=x.get("adresse", ""), categorie=x.get("categorie", "autre"), prix=x.get("prix", ""),
                description=x.get("description") or "Rendez-vous de chaque semaine : à confirmer auprès du lieu."))
    return res


def recuperer(source: dict) -> list[Evenement]:
    entrees = yaml.safe_load(FICHIER.read_text()) if FICHIER.exists() else []
    return evenements(entrees or [])
