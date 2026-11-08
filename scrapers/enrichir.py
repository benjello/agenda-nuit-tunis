"""Fiches plus riches, depuis des sources ouvertes et gratuites :

- photos des artistes et des lieux : Wikidata (propriété P18, image sur Wikimedia Commons) ;
- accès fauteuil, horaires, site et type (cinéma, théâtre…) des lieux et des musées : OpenStreetMap (Overpass),
  une seule requête pour toute la Tunisie.

Les réponses sont gardées dans _data/enrichi.json (clé : identifiant de la fiche) pour ne pas
réinterroger chaque jour : un nom déjà cherché n'est recherché à nouveau qu'après 30 jours.

  python3 -m scrapers.enrichir
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata

import requests
import yaml

from .commun import RACINE
from .doublons import _lire
from .wikidata import TUNISIE, UA, _api, _entites, _valeurs

FICHIER = RACINE / "_data" / "enrichi.json"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
MAX_RECHERCHES = 60          # recherches Wikidata par passage
REESSAI_JOURS = 30
HUMAIN = "Q5"
P_IMAGE, P_NATURE, P_PAYS, P_NATIONALITE = "P18", "P31", "P17", "P27"

# Lieux culturels dans OpenStreetMap
REQUETE_OSM = """[out:json][timeout:120];
area["ISO3166-1"="TN"][admin_level=2]->.tn;
(
  nwr["tourism"~"^(museum|gallery)$"](area.tn);
  nwr["amenity"~"^(theatre|cinema|arts_centre|library|community_centre)$"](area.tn);
);
out tags center;"""


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\b(le|la|les|l|de|du|des|d|et|the|of)\b", " ", re.sub(r"[^a-z0-9 ]", " ", t))
    return " ".join(t.split())


def commons(fichier: str, largeur: int = 400) -> dict:
    nom = fichier.replace(" ", "_")
    return {"image": f"https://commons.wikimedia.org/wiki/Special:FilePath/{nom}?width={largeur}",
            "credit": f"https://commons.wikimedia.org/wiki/File:{nom}"}


def acceptable(e: dict, genre: str) -> bool:
    """Un artiste : une personne tunisienne ; un lieu : en Tunisie. Évite les homonymes."""
    if genre == "artiste":
        return HUMAIN in _valeurs(e, P_NATURE) and TUNISIE in _valeurs(e, P_NATIONALITE)
    return TUNISIE in _valeurs(e, P_PAYS)


def image_wikidata(nom: str, genre: str) -> dict | None:
    trouves = _api(action="wbsearchentities", search=nom, language="fr", uselang="fr", limit=5).get("search", [])
    ids = [t["id"] for t in trouves]
    if not ids:
        return None
    entites = _entites(ids)
    for i in ids:
        e = entites.get(i) or {}
        images = _valeurs(e, P_IMAGE)
        if images and acceptable(e, genre):
            return {"qid": i, **commons(images[0])}
    return None


def fiches(dossier: str) -> list[tuple[str, str]]:
    res = []
    for f in sorted((RACINE / dossier).glob("*.md")):
        c, _ = _lire(f)
        if c and c.get("title"):
            res.append((f.stem, str(c["title"]).split(",")[0].strip()))
    return res


# Étiquette OpenStreetMap → type de lieu du site (_data/types_lieux.yml)
TYPES_OSM = {"cinema": "cinema", "theatre": "theatre", "gallery": "galerie", "museum": "musee",
             "library": "bibliotheque", "arts_centre": "centre_art", "community_centre": "centre"}


def osm_index(elements: list[dict]) -> dict:
    """{nom normalisé : étiquettes utiles}"""
    res = {}
    for el in elements:
        t = el.get("tags") or {}
        infos = {k: t[k] for k in ("wheelchair", "opening_hours", "website") if t.get(k)}
        genre = TYPES_OSM.get(t.get("amenity") or "") or TYPES_OSM.get(t.get("tourism") or "")
        if genre:
            infos["type"] = genre
        if not infos:
            continue
        for cle in ("name", "name:fr", "name:en", "name:ar"):
            if t.get(cle):
                res.setdefault(_norm(t[cle]), infos)
    return res


def chercher_osm(index: dict, nom: str) -> dict | None:
    n = _norm(nom)
    if not n:
        return None
    if n in index:
        return index[n]
    # « Théâtre municipal de Tunis » ↔ « Théâtre municipal » : un nom contient l'autre (3 mots au moins)
    for k, v in index.items():
        court, long_ = sorted((k, n), key=len)
        if len(court.split()) >= 3 and court in long_:
            return v
    return None


def _overpass(requete: str) -> list[dict]:
    """Essaie les serveurs Overpass l'un après l'autre (souvent saturés)."""
    erreur = None
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": requete}, headers=UA, timeout=180)
            r.raise_for_status()
            return r.json().get("elements", [])
        except (requests.RequestException, ValueError) as exc:
            erreur = exc
    raise erreur


def lire() -> dict:
    try:
        d = json.loads(FICHIER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        d = {}
    return {"images": d.get("images") or {}, "osm": d.get("osm") or {}, "vu": d.get("vu") or {}}


def main() -> int:
    cache = lire()
    aujourd_hui = dt.date.today()
    limite = (aujourd_hui - dt.timedelta(days=REESSAI_JOURS)).isoformat()
    # 1. Photos (Wikidata)
    n = 0
    for genre, dossier in (("artiste", "_artistes"), ("lieu", "_lieux")):
        for cle, nom in fiches(dossier):
            k = f"{genre}:{cle}"
            if k in cache["images"] or cache["vu"].get(k, "") > limite or n >= MAX_RECHERCHES:
                continue
            n += 1
            try:
                r = image_wikidata(nom, genre)
            except (requests.RequestException, ValueError) as exc:
                print(f"  wikidata : {nom} : {exc}")
                break
            cache["vu"][k] = aujourd_hui.isoformat()
            if r:
                cache["images"][k] = r
                print(f"  photo : {nom} → {r['qid']}")
    # 2. Accès, horaires (OpenStreetMap)
    try:
        index = osm_index(_overpass(REQUETE_OSM))
        musees = yaml.safe_load((RACINE / "_data" / "musees.yml").read_text()) or []
        osm = {}
        for cle, nom in fiches("_lieux"):
            t = chercher_osm(index, nom)
            if t:
                osm[f"lieu:{cle}"] = t
                print(f"  OSM : {nom} → {t}")
        for m in musees:
            t = chercher_osm(index, m["nom"]) or next((chercher_osm(index, x) for x in m.get("mots") or [] if chercher_osm(index, x)), None)
            if t:
                osm[f"musee:{m['nom']}"] = t
        cache["osm"] = osm
    except (requests.RequestException, ValueError) as exc:
        print(f"  OpenStreetMap : {exc} (on garde les données d'avant)")
    FICHIER.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"Fiches enrichies : {len(cache['images'])} photos, {len(cache['osm'])} lieux avec accès ou horaires "
          f"({n} recherche(s) Wikidata)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
