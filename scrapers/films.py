"""Regroupe les films à l'affiche par film, toutes salles confondues.

Chaque source écrit un événement par film et par salle (« BAKMA » au Colisée, « BAKMA - بكمة »
au Palace…). Pour la page Cinéma, on veut l'inverse : un film, puis les salles qui le jouent
et leurs jours. Ce module lit les événements « film: true » de _events/auto et écrit
_data/films.json, lu par la page d'accueil. Chaque film y reçoit aussi ses articles de presse
(scrapers/critiques.py) et la liste des fiches de ses séances, pour l'encadré de event.html.

Deux titres désignent le même film s'ils partagent un morceau : « LAST CHANCE - لص شايح »
et « لص شايح », ou « WEEKEND » et « Weekend ». L'affiche vient de la première salle qui en a une.

Lancé automatiquement à la fin de « python3 -m scrapers ».
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata

import yaml
from pathlib import Path

from .commun import RACINE, slug
from .doublons import _lire
from .ecriture import DOSSIER_AUTO

FICHIER = RACINE / "_data" / "films.json"
_HARAKAT = re.compile("[ً-ْٰـ]")


def morceaux(titre: str) -> set[str]:
    """« LAST CHANCE - لص شايح » → {« last chance », « لص شايح »} (minuscules, sans accents)."""
    t = _HARAKAT.sub("", unicodedata.normalize("NFKC", titre))
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    parts = re.split(r"\s+[-–/|]\s+|\s*[/|]\s*", t)
    return {p for p in (re.sub(r"[^\w]+", " ", x).strip().lower() for x in parts) if len(p) >= 3}


def _heures(champs: dict) -> dict[str, list[str]]:
    """{« AAAA-MM-JJ » : [« HH:MM », …]} pour les séances dont l'heure est connue."""
    res: dict[str, set] = {}
    for s in champs.get("seances") or [champs.get("date")]:
        s = str(s or "")
        if len(s) >= 16 and s[11:16] != "00:00":
            res.setdefault(s[:10], set()).add(s[11:16])
    return {j: sorted(h) for j, h in res.items()}


def _jours(champs: dict) -> list[str]:
    jours = champs.get("seances") or [champs.get("date")]
    return sorted({str(j)[:10] for j in jours if j})


def regrouper(dossier: Path = DOSSIER_AUTO) -> list[dict]:
    aujourd_hui = dt.date.today().isoformat()
    seances = []
    for f in sorted(dossier.glob("*/*.md")):
        champs, _ = _lire(f)
        if champs and champs.get("film") and champs.get("title"):
            jours = [j for j in _jours(champs) if j >= aujourd_hui]
            if jours:
                seances.append((champs, morceaux(champs["title"]) or {champs["title"].lower()}, jours,
                                f.relative_to(RACINE).as_posix() if f.is_relative_to(RACINE) else f.as_posix()))

    # Union des titres qui partagent un morceau.
    groupes: list[dict] = []
    for champs, cles, jours, chemin in seances:
        lies = [g for g in groupes if g["cles"] & cles]
        g = {"cles": set(cles), "items": [], "fichiers": []}
        for autre in lies:
            g["cles"] |= autre["cles"]
            g["items"] += autre["items"]
            g["fichiers"] += autre["fichiers"]
            groupes.remove(autre)
        g["items"].append((champs, jours))
        g["fichiers"].append(chemin)
        groupes.append(g)

    films = []
    for g in groupes:
        items = g["items"]
        # Titre affiché : le plus complet (« BAKMA - بكمة » plutôt que « BAKMA »).
        titre = max((c["title"] for c, _ in items), key=lambda t: (len(morceaux(t)), len(t)))
        premier = lambda cle: next((c[cle] for c, _ in items if c.get(cle)), None)  # noqa: E731
        salles: dict[str, dict] = {}
        for c, jours in items:
            s = salles.setdefault(slug(c.get("venue", ""))[:20], {
                "nom": c.get("venue", ""), "adresse": c.get("address", ""), "lien": c.get("link", ""),
                "source": c.get("source", ""), "source_nom": c.get("source_name", ""), "jours": set(), "heures": {}})
            s["jours"] |= set(jours)
            for j, h in _heures(c).items():
                if j in jours:
                    s["heures"][j] = sorted(set(s["heures"].get(j, [])) | set(h))
        salles_l = sorted(salles.values(), key=lambda s: s["nom"])
        for s in salles_l:
            s["jours"] = sorted(s["jours"])
            s["heures"] = [{"jour": j, "heures": s["heures"][j]} for j in sorted(s["heures"])]
        films.append({
            "titre": titre, "id": slug(titre) or titre,
            "image": premier("image") or "", "imdb": premier("imdb") or "",
            "duree": premier("duration"), "genres": premier("genres") or [],
            "jours": sorted({j for s in salles_l for j in s["jours"]}),
            "salles": salles_l,
            # Les fiches des séances (page.path) : event.html y retrouve le film et sa presse.
            "fichiers": sorted(g["fichiers"]),
        })
    # Les films qui passent dans le plus de salles d'abord, puis par titre.
    films.sort(key=lambda f: (-len(f["salles"]), f["titre"].lower()))
    return films


_JEUNE = re.compile(r"animation|anim[ée]|famil|enfant|jeunesse", re.I)


def typologie(films: list[dict]) -> None:
    """Corrections à la main (_data/films_infos.yml), puis « jeune public » :
    tous publics et film d'animation ou familial, ou séance pour enfants (Mercredis-Ciné…)."""
    try:
        infos = yaml.safe_load((RACINE / "_data" / "films_infos.yml").read_text()) or {}
    except FileNotFoundError:
        infos = {}
    infos = {slug(k): v for k, v in infos.items()}
    for f in films:
        f.update(infos.get(slug(f["titre"]), {}))
        genres = " ".join(f.get("genres") or [])
        f["jeune"] = bool(f.get("jeune") or (_JEUNE.search(genres) and f.get("age", "") in ("", "Tous publics", None)))


def ecrire(dossier: Path = DOSSIER_AUTO, fichier: Path = FICHIER, enrichir: bool = True) -> int:
    films = regrouper(dossier)
    if enrichir:
        from . import wikidata
        wikidata.completer(films, morceaux)  # genres, âge, IMDb, film tunisien
    typologie(films)
    from . import critiques
    critiques.rattacher(films)  # « Ce qu'en dit la presse »
    fichier.write_text(json.dumps(films, ensure_ascii=False, indent=1) + "\n")
    return len(films)
