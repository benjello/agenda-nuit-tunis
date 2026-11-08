"""Traduction des libellés : lieux, adresses, festivals, musées, descriptifs, prix…

Tout ce que le site affiche, hors titre d'événement, doit être dans la langue choisie.
On rassemble ici les textes courts ou moyens (pas les notices d'événements, traitées par
traduire.py), on les traduit une seule fois avec les mêmes modèles libres (Argos Translate)
et on les garde dans _data/libelles.json :

  { texte d'origine : { de, en, ar } }      (de : langue d'origine ; sans cette langue-là dans en/ar)

Le fichier libelles.json du site (racine) l'expose ; assets/site.js remplace, quand on choisit
عربي ou EN, chaque texte de la page qui correspond exactement à une clé.

  python3 -m scrapers.libelles
"""
from __future__ import annotations

import json
import re
import time

import yaml

from .commun import RACINE
from .doublons import _lire
from .traduire import LANGUES, Traducteur, a_traduire, langue

FICHIER = RACINE / "_data" / "libelles.json"
MAX_TEXTES = 500
MAX_SECONDES = 15 * 60
MAX_LONGUEUR = 1500
# clés dont le contenu n'est pas du texte affiché (motifs, identifiants, liens…)
IGNORER = {"mots", "motifs", "regex", "id", "slug", "lien", "url", "image", "source", "sources", "noms",
           "type", "genre", "ville", "date", "debut", "fin", "licence", "cle", "alias"}
FICHIERS_DATA = ["festivals.yml", "musees.yml", "types_lieux.yml", "categories.yml", "villes.yml",
                 "ramadan.yml", "series.yml", "genres.yml", "artistes.yml", "descriptifs_manuels.yml",
                 "films_infos.yml", "lieux_references.yml"]
JSON_DATA = ["descriptifs.json", "films.json", "lieux.json", "presse.json", "enrichi.json"]
CHAMPS_EVENT = ("venue", "address", "price", "source_name", "festival")
CHAMPS_PAGE = ("title", "adresse", "nom", "description")


def retenu(texte, court: bool = False) -> bool:
    if not isinstance(texte, str):
        return False
    t = texte.strip()
    if not t or len(t) > MAX_LONGUEUR or "http" in t or re.search(r"[\\^$]|\[\^|\(\?", t):
        return False
    if re.search(r"\b(?:Mo|Tu|We|Th|Fr|Sa|Su)\b[ -]|\d\s*DT\b|\bPH off\b", t):  # horaires OSM et prix : traités par le script
        return False
    if re.fullmatch(r"[\d\W]+", t) or re.fullmatch(r"[a-z0-9_-]+", t):
        return False
    return a_traduire(t) or (court and bool(re.fullmatch(r"[^\W\d_]{4,}", t)))


def feuilles(o, cle=""):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if str(k) not in IGNORER:
                yield from feuilles(v, str(k))
    elif isinstance(o, list):
        for v in o:
            yield from feuilles(v, cle)


COURTS = {"categories.yml", "types_lieux.yml", "villes.yml", "genres.yml"}   # un mot suffit (« Théâtre »)


def titres_evenements() -> set[str]:
    """Titres d'événements (listes des festivals, cinéma…) : déjà traduits par traduire.py."""
    from .traduire import lire as lire_titres
    return set(lire_titres()["titres"])


def textes_du_site() -> set[str]:
    res: set[str] = set()

    def ajouter(valeurs, court=False):
        res.update(t.strip() for t in valeurs if retenu(t, court))

    for f in FICHIERS_DATA:
        try:
            ajouter(feuilles(yaml.safe_load((RACINE / "_data" / f).read_text()) or []), f in COURTS)
        except FileNotFoundError:
            pass
    for f in JSON_DATA:
        try:
            ajouter(feuilles(json.loads((RACINE / "_data" / f).read_text())))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    for dossier in ("_events", "_lieux", "_collectifs", "_artistes"):
        champs_voulus = CHAMPS_EVENT if dossier == "_events" else CHAMPS_PAGE
        for f in sorted((RACINE / dossier).rglob("*.md")):
            if f.name == "README.md":
                continue
            champs, _ = _lire(f)
            for k in champs_voulus:
                if k == "title" and dossier == "_events":
                    continue
                # lieux et adresses : un mot suffit (« Médiathèque », « Gabès »)
                court = k in ("venue", "address", "adresse", "title")
                for v in feuilles((champs or {}).get(k)):
                    ajouter([v], court)
                    if court and "," in v:   # « Gabès, voir l'annonce » : chaque morceau compte aussi
                        ajouter(v.split(","), True)
    res.update(titres_evenements())
    return res


def lire() -> dict:
    try:
        return json.loads(FICHIER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def traduire_libelles(traducteur, cache: dict, textes: set[str]) -> int:
    debut, n = time.monotonic(), 0
    restants = sorted((t for t in textes if t not in cache), key=lambda t: (len(t), t))[:MAX_TEXTES]
    for de in LANGUES:
        lot = [t for t in restants if langue(t) == de]
        for i in range(0, len(lot), 25):
            if time.monotonic() - debut > MAX_SECONDES:
                print("  libellés : temps écoulé, la suite au prochain passage")
                return n
            paquet = lot[i:i + 25]
            entrees = [{"de": de} for _ in paquet]
            for vers in LANGUES:
                if vers != de:
                    for e, tr in zip(entrees, traducteur.traduire(paquet, de, vers)):
                        e[vers] = tr
            for t, e in zip(paquet, entrees):
                cache[t] = e
            n += len(paquet)
    return n


def main(argv=None) -> int:
    try:
        traducteur = Traducteur()
    except ImportError:
        print("libellés : installer ctranslate2 et sentencepiece (pip install -r requirements-traduction.txt)")
        return 0
    cache, textes = lire(), textes_du_site()
    from .traduire import lire as lire_titres
    for t, v in lire_titres()["titres"].items():   # déjà traduits : rien à refaire
        de = langue(t)
        if t not in cache and all(v.get(x) for x in LANGUES if x != de):
            cache[t] = {"de": de, **{x: v[x] for x in LANGUES if x != de}}
    n = traduire_libelles(traducteur, cache, textes) if any(t not in cache for t in textes) else 0
    cache = {k: v for k, v in sorted(cache.items()) if k in textes}
    FICHIER.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n")
    print(f"Libellés : {n} texte(s) traduit(s), {len(cache)} en tout sur {len(textes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
