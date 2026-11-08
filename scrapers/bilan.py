"""Bilan de couverture, semaine par semaine : combien d'événements, par source et par ville.

Chaque passage des scrapers met à jour la ligne de la semaine en cours dans
_data/bilan.json (une ligne par semaine, les 52 dernières). La page /couverture/
montre la semaine en cours et l'évolution.

Compté : les événements à venir dans les 7 jours (doublons masqués exclus) et tous
ceux à venir. Un film compte une fois, quel que soit le nombre de salles.

  python3 -m scrapers.bilan
"""
from __future__ import annotations

import collections
import datetime as dt
import json

import yaml

from .commun import RACINE
from .traduire import evenements

FICHIER = RACINE / "_data" / "bilan.json"
SEMAINES = 52


def _jour(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def compter(evts: list[dict], aujourd_hui: dt.date, sources: list[dict]) -> dict:
    genres = {s["id"]: s.get("genre", "lieu") for s in sources}
    semaine = aujourd_hui + dt.timedelta(days=7)
    par_source, par_ville, par_cat, par_genre = (collections.Counter() for _ in range(4))
    total, sept, films = 0, 0, set()
    for c in evts:
        debut, fin = _jour(c.get("date")), _jour(c.get("end_date")) or _jour(c.get("date"))
        if not debut or fin < aujourd_hui:
            continue
        if c.get("film"):
            if c.get("title") in films:
                continue
            films.add(c.get("title"))
        total += 1
        if debut > semaine:
            continue
        sept += 1
        par_source[c.get("source") or "manuel"] += 1
        par_ville[c.get("ville") or "tunis"] += 1
        par_cat[c.get("category") or "autre"] += 1
        par_genre[genres.get(c.get("source"), "manuel")] += 1
    actives = [s for s in sources if s.get("actif", True)]
    an, sem, _ = aujourd_hui.isocalendar()
    return {
        "semaine": f"{an}-S{sem:02d}", "date": aujourd_hui.isoformat(),
        "a_venir": total, "sept_jours": sept,
        "sources_actives": len(actives), "sources_avec_evenements": len(par_source),
        "sources_muettes": sorted(s["id"] for s in actives if s["id"] not in par_source),
        "par_ville": dict(par_ville.most_common()), "par_categorie": dict(par_cat.most_common()),
        "par_genre": dict(par_genre.most_common()), "par_source": dict(par_source.most_common()),
    }


def main() -> int:
    sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []
    ligne = compter([c for _, c, _ in evenements()], dt.date.today(), sources)
    try:
        hist = json.loads(FICHIER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        hist = []
    hist = [h for h in hist if h.get("semaine") != ligne["semaine"]] + [ligne]
    hist = sorted(hist, key=lambda h: h["semaine"])[-SEMAINES:]
    FICHIER.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n")
    print(f"Bilan {ligne['semaine']} : {ligne['sept_jours']} événements dans les 7 jours, {ligne['a_venir']} à venir, "
          f"{ligne['sources_avec_evenements']}/{ligne['sources_actives']} sources")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
