"""Fiche des films à l'affiche depuis Wikidata (données libres, CC0).

Pour chaque film, on cherche son élément Wikidata par le titre (français, anglais, arabe),
en ne gardant que les films récents qui ont un identifiant IMDb. On en tire :
  imdb     identifiant IMDb exact (tt…)
  genres   ramenés à une liste courte (Drame, Comédie, Animation…)
  age      classement français : Tous publics, -12, -16, -18 (quand Wikidata le connaît)
  tunisien film produit en Tunisie (pays d'origine)

Les réponses sont gardées dans _data/wikidata.json pour ne pas réinterroger Wikidata chaque
jour ; un film introuvable est recherché de nouveau après une semaine.
"""
from __future__ import annotations

import datetime as dt
import json
import re

import requests

from .commun import RACINE

CACHE = RACINE / "_data" / "wikidata.json"
API = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "agenda-nuit-tunis/1.0 (https://github.com/benjello/agenda-nuit-tunis)"}
TUNISIE = "Q948"
P_IMDB, P_GENRE, P_PAYS, P_DATE, P_NATURE = "P345", "P136", "P495", "P577", "P31"
P_LETTERBOXD = "P6127"  # identifiant Letterboxd du film (sa « slug », CC0 comme le reste de Wikidata)
FILM = "Q11424"
P_AGE_CNC = "P2758"  # classement CNC (France)
LANGUES = ("fr", "en", "ar")

# Genres Wikidata (libellés français, très nombreux) → liste courte affichée sur le site.
GENRES = [
    (r"anim", "Animation"), (r"comédie dramatique", "Comédie dramatique"), (r"comédie|comique", "Comédie"),
    (r"documentaire", "Documentaire"), (r"horreur|épouvante", "Horreur"), (r"thriller|suspense", "Thriller"),
    (r"science-fiction", "Science-fiction"), (r"fantas|merveilleux", "Fantastique"), (r"action", "Action"),
    (r"aventure", "Aventure"), (r"famil|enfant|jeunesse", "Familial"), (r"roman(ce|tique)", "Romance"),
    (r"policier|crim|gangster|noir", "Policier"), (r"guerre", "Guerre"), (r"histor", "Historique"),
    (r"biograph", "Biopic"), (r"music", "Musical"), (r"western", "Western"), (r"drame|dramatique", "Drame"),
]
AGES = [(r"tous publics|tout public", "Tous publics"), (r"12", "-12"), (r"16", "-16"), (r"18", "-18")]


def _api(**params) -> dict:
    r = requests.get(API, params={"format": "json", **params}, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def _valeurs(entite: dict, prop: str) -> list:
    res = []
    for c in entite.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            res.append(v["id"])
        elif isinstance(v, dict) and "time" in v:
            res.append(v["time"])
        elif v is not None:
            res.append(v)
    return res


def _annee(entite: dict) -> int:
    annees = [int(t[1:5]) for t in _valeurs(entite, P_DATE) if isinstance(t, str) and t[1:5].isdigit()]
    return max(annees) if annees else 0


def _entites(ids: list[str]) -> dict:
    res = {}
    for i in range(0, len(ids), 40):
        res.update(_api(action="wbgetentities", ids="|".join(ids[i:i + 40]),
                        props="claims|labels", languages="fr|en").get("entities", {}))
    return res


def _libelle(e: dict) -> str:
    lab = e.get("labels", {})
    return (lab.get("fr") or lab.get("en") or {}).get("value", "")


def chercher(morceaux: list[str], annee_min: int) -> dict | None:
    """L'élément Wikidata le plus récent d'un film qui a un identifiant IMDb, ou None."""
    ids = []
    for m in morceaux:
        for langue in LANGUES:
            for r in _api(action="wbsearchentities", search=m, language=langue, uselang="fr",
                          type="item", limit=7).get("search", []):
                if r["id"] not in ids:
                    ids.append(r["id"])
    if not ids:
        return None
    def est_film(e):
        return any(str(v).startswith("tt") for v in _valeurs(e, P_IMDB)) or FILM in _valeurs(e, P_NATURE)

    def recent(e):
        # Les films tunisiens récents n'ont souvent pas encore de date de sortie sur Wikidata.
        return _annee(e) >= annee_min or (_annee(e) == 0 and TUNISIE in _valeurs(e, P_PAYS))
    films = [(qid, e) for qid, e in _entites(ids).items() if est_film(e) and recent(e)]
    if not films:
        return None
    qid, e = max(films, key=lambda f: _annee(f[1]))
    return {"qid": qid, "entite": e}


def fiche(qid: str, e: dict) -> dict:
    """Ce qu'on garde d'un film : imdb, letterboxd, genres (liste courte), age, tunisien."""
    genres_q = _valeurs(e, P_GENRE)
    ages_q = _valeurs(e, P_AGE_CNC)
    libelles = {q: _libelle(x) for q, x in _entites(genres_q + ages_q).items()} if genres_q or ages_q else {}
    genres = []
    for q in genres_q:
        lab = libelles.get(q, "").lower()
        g = next((nom for motif, nom in GENRES if re.search(motif, lab)), None)
        if g and g not in genres:
            genres.append(g)
    if "Comédie dramatique" in genres:
        genres = [g for g in genres if g not in ("Comédie", "Drame")]
    age = ""
    for q in ages_q:
        age = next((nom for motif, nom in AGES if re.search(motif, libelles.get(q, "").lower())), age)
    return {"qid": qid, "imdb": next((v for v in _valeurs(e, P_IMDB) if str(v).startswith("tt")), ""),
            "letterboxd": next((str(v) for v in _valeurs(e, P_LETTERBOXD) if isinstance(v, str) and v), ""),
            "genres": genres[:3], "age": age, "tunisien": TUNISIE in _valeurs(e, P_PAYS),
            "annee": _annee(e), "titre_wikidata": _libelle(e)}


def lire_cache() -> dict:
    try:
        return json.loads(CACHE.read_text())
    except (OSError, ValueError):
        return {}


def completer(films: list[dict], morceaux_de) -> None:
    """Ajoute à chaque film ce que Wikidata en sait (sur place). Ne lève jamais d'erreur."""
    cache, aujourd_hui = lire_cache(), dt.date.today()
    for f in films:
        cle = f["id"]
        c = cache.get(cle)
        a_refaire = c is None or (c.get("qid") is None and
                                  aujourd_hui - dt.date.fromisoformat(c["verifie"]) > dt.timedelta(days=7)) \
            or (c.get("qid") and "letterboxd" not in c)  # notices écrites avant l'ajout de Letterboxd
        if a_refaire:
            try:
                trouve = chercher(sorted(morceaux_de(f["titre"])), aujourd_hui.year - 3)
                c = fiche(trouve["qid"], trouve["entite"]) if trouve else {"qid": None}
                c["verifie"] = aujourd_hui.isoformat()
                cache[cle] = c
                print(f"  wikidata · {f['titre']} → {c.get('qid')} {c.get('titre_wikidata', '')} "
                      f"{c.get('genres', '')} {c.get('age', '')}{' tunisien' if c.get('tunisien') else ''}")
            except Exception as exc:  # noqa: BLE001 — Wikidata en panne : on garde les films tels quels
                print(f"  wikidata · {f['titre']} : {type(exc).__name__}: {exc}")
                continue
        if c and c.get("qid"):
            f["wikidata"] = c["qid"]
            f["imdb"] = f.get("imdb") or c.get("imdb", "")
            f["letterboxd"] = c.get("letterboxd", "")
            f["genres"] = f.get("genres") or c.get("genres", [])
            f["age"] = c.get("age", "")
            f["tunisien"] = bool(c.get("tunisien"))
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
