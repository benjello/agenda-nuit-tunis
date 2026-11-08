"""Cinémas Pathé (pathe.tn, même plateforme que pathe.fr).

On lit d'abord l'API JSON du site, puis la page HTML du cinéma en repli.
Options : cinema = identifiant du cinéma dans l'adresse (cinema-pathe-tunis-city).
Note : pathe.tn refuse (erreur 403) les requêtes venant des serveurs de GitHub.
Lancé depuis un ordinateur ou un serveur ordinaire, il devrait passer.
"""
from __future__ import annotations

import datetime as dt
import re

from ..commun import Evenement, film, page, propre, telecharger_json

BASE = "https://www.pathe.tn"
JOURS = 7


def _affiche(info: dict):
    p = info.get("posterPath")
    if isinstance(p, dict):
        p = p.get("md") or p.get("lg") or next(iter(p.values()), None)
    return p if isinstance(p, str) and p.startswith("http") else None


def films_depuis_api(seances: dict, catalogue: dict, aujourd_hui: dt.date, salle: str = "Pathé") -> list[Evenement]:
    debut, fin = aujourd_hui.isoformat(), (aujourd_hui + dt.timedelta(days=JOURS)).isoformat()
    films = []
    for slug_film, s in (seances.get("shows", seances) or {}).items():
        jours = sorted(d[:10] for d in (s.get("days") or {}) if debut <= d[:10] <= fin)
        if not jours:
            continue
        info = catalogue.get(slug_film, {})
        films.append(film(
            info.get("title") or slug_film.replace("-", " ").capitalize(),
            f"{BASE}/fr/films/{slug_film}", salle, jours, duree=info.get("duration"),
            genres=info.get("genres") or [], image=_affiche(info) or ""))
    return films


def films_depuis_html(soup, salle: str = "Pathé") -> list[Evenement]:
    """Repli : la page ne donne pas les jours ; on compte le film à l'affiche aujourd'hui."""
    films, vus = [], set()
    for a in soup.find_all("a", href=re.compile(r"^/fr/films/[a-z0-9-]+")):
        slug_film = a["href"].split("/")[3]
        titre = propre(a.get_text(" "))
        if slug_film in vus or not titre:
            continue
        vus.add(slug_film)
        films.append(film(titre, f"{BASE}/fr/films/{slug_film}", salle, [dt.date.today().isoformat()]))
    return films


def recuperer(source: dict) -> list[Evenement]:
    cinema = source["options"]["cinema"]
    salle = source["options"].get("lieu") or source["nom"]
    try:
        cat = telecharger_json(f"{BASE}/api/shows?language=fr")
        liste = cat.get("shows", cat) if isinstance(cat, dict) else cat
        catalogue = {s["slug"]: s for s in liste if isinstance(s, dict) and s.get("slug")}
    except Exception:  # noqa: BLE001 — le catalogue ne sert qu'à enrichir
        catalogue = {}
    try:
        films = films_depuis_api(telecharger_json(f"{BASE}/api/cinema/{cinema}/shows?language=fr"),
                                 catalogue, dt.date.today(), salle)
        if films:
            return films
    except Exception:  # noqa: BLE001
        pass
    films = films_depuis_html(page(f"{BASE}/fr/cinemas/{cinema}"), salle)
    if not films:
        raise RuntimeError("aucun film trouvé, ni par l'API ni sur la page du cinéma")
    return films
