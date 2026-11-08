"""Clubs, discothèques, bars et pubs de Tunisie, avec leurs horaires, pour la page /clubs/.

Ce sont les lieux de sortie « habituels » : ils ouvrent chaque semaine, même sans soirée spéciale annoncée.
Source : OpenStreetMap (Overpass, licence ODbL), complété et corrigé à la main par `_data/clubs.yml`.
Écrit `_data/clubs.json`. Relu une fois par semaine (les lieux changent peu).

Usage : python3 -m scrapers.clubs [--force]
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys

import yaml

from .commun import RACINE
from .enrichir import _overpass
from .villes import ville

FICHIER = RACINE / "_data" / "clubs.json"
MANUEL = RACINE / "_data" / "clubs.yml"
JOURS_ENTRE_DEUX = 7

REQUETE = """[out:json][timeout:120];
area["ISO3166-1"="TN"][admin_level=2]->.tn;
(
  nwr["amenity"~"^(nightclub|bar|pub|karaoke_box)$"](area.tn);
  nwr["amenity"="restaurant"]["cuisine"~"cabaret"](area.tn);
);
out tags center;"""

# amenity OpenStreetMap → type affiché sur la page (même clés que _data/categories.yml)
TYPES = {"nightclub": "club", "bar": "bar", "pub": "bar", "karaoke_box": "karaoke", "restaurant": "cabaret"}

_JOURS = {"Mo": "lun", "Tu": "mar", "We": "mer", "Th": "jeu", "Fr": "ven", "Sa": "sam", "Su": "dim", "PH": "fériés"}


def horaires_fr(oh: str) -> str:
    """« Th-Sa 23:00-05:00; Su off » → « jeu-sam 23h-5h ; dim fermé ». Le reste est gardé tel quel."""
    if not oh:
        return ""
    t = re.sub(r"\b(Mo|Tu|We|Th|Fr|Sa|Su|PH)\b", lambda m: _JOURS[m.group(1)], oh)
    t = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: f"{int(m.group(1))}h" + ("" if m.group(2) == "00" else m.group(2)), t)
    t = t.replace("24/7", "tous les jours, 24 h/24").replace(" off", " fermé").replace("off", "fermé")
    return re.sub(r"\s*;\s*", " ; ", t).strip()


def depuis_osm(elements: list[dict]) -> list[dict]:
    lieux = []
    for el in elements:
        t = el.get("tags") or {}
        nom = (t.get("name:fr") or t.get("name") or t.get("name:en") or "").strip()
        if not nom:
            continue
        adresse = ", ".join(x for x in (
            " ".join(y for y in (t.get("addr:housenumber"), t.get("addr:street")) if y),
            t.get("addr:suburb") or t.get("addr:place"), t.get("addr:city")) if x)
        centre = el.get("center") or el
        insta = t.get("contact:instagram") or t.get("instagram") or ""
        lieux.append({
            "nom": nom,
            "type": TYPES.get(t.get("amenity"), "bar"),
            "ville": ville(nom, adresse, t.get("addr:city", "")),
            "adresse": adresse,
            "horaires": horaires_fr(t.get("opening_hours", "")),
            "site": t.get("website") or t.get("contact:website") or "",
            "instagram": insta.rstrip("/").split("/")[-1].lstrip("@") if insta else "",
            "facebook": t.get("contact:facebook") or t.get("facebook") or "",
            "telephone": t.get("phone") or t.get("contact:phone") or "",
            "lat": centre.get("lat"), "lon": centre.get("lon"),
            "osm": f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}",
            # Ambiance : style de musique (music:genre, peu rempli) et terrasse ; le reste vient de clubs.yml.
            "ambiance": ", ".join(x for x in ((t.get("music:genre") or t.get("music") or "").replace(";", ", "),
                                              "terrasse" if t.get("outdoor_seating") == "yes" else "") if x),
            "age_min": t.get("min_age", ""),
        })
    return lieux


def fusionner(osm: list[dict], manuel: list[dict]) -> list[dict]:
    """Les entrées de clubs.yml corrigent celles d'OpenStreetMap (même nom) ou s'y ajoutent."""
    cle = lambda n: re.sub(r"[^a-z0-9]", "", (n or "").lower())  # noqa: E731
    par_nom = {cle(x["nom"]): x for x in osm}
    for m in manuel or []:
        if m.get("cacher"):
            par_nom.pop(cle(m.get("nom")), None)
            continue
        base = par_nom.get(cle(m.get("nom")), {"nom": m.get("nom"), "type": "club", "ville": ville(m.get("nom", ""), m.get("adresse", ""))})
        base.update({k: v for k, v in m.items() if v not in (None, "")})
        base["manuel"] = True
        par_nom[cle(base["nom"])] = base
    lieux = [{k: v for k, v in x.items() if v not in (None, "")} for x in par_nom.values()]  # champs vides retirés : la page n'affiche que ce qu'on sait
    return sorted(lieux, key=lambda x: (x.get("ville", ""), x.get("type", ""), x["nom"].lower()))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        ancien = json.loads(FICHIER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        ancien = {}
    if ancien.get("lu_le") and "--force" not in argv:
        age = (dt.date.today() - dt.date.fromisoformat(ancien["lu_le"])).days
        if age < JOURS_ENTRE_DEUX:
            print(f"clubs : liste lue il y a {age} jour(s), pas de nouvelle lecture.")
            return 0
    manuel = yaml.safe_load(MANUEL.read_text()) if MANUEL.exists() else []
    try:
        osm = depuis_osm(_overpass(REQUETE))
    except Exception as exc:  # noqa: BLE001 — Overpass saturé : on garde l'ancienne liste
        print(f"clubs : OpenStreetMap illisible ({exc}), ancienne liste gardée.")
        return 0
    lieux = fusionner(osm, manuel)
    FICHIER.write_text(json.dumps({"lu_le": dt.date.today().isoformat(), "source": "OpenStreetMap (ODbL) et _data/clubs.yml",
                                   "lieux": lieux}, ensure_ascii=False, indent=1))
    avec_insta = [x for x in lieux if x.get("instagram")]
    print(f"clubs : {len(lieux)} lieu(x), dont {sum(bool(x.get('horaires')) for x in lieux)} avec horaires "
          f"et {len(avec_insta)} avec un compte Instagram (sources possibles) :")
    for x in avec_insta:
        print(f"  - @{x['instagram']} | {x['nom']} | {x['ville']} | {x['type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
