"""Fiches du site faites à partir des événements : lieux, organisateurs, artistes.

GitHub Pages ne fait pas tourner d'extension Jekyll : une fiche = un fichier.
Ce script écrit, après chaque passage des scrapers :
- _lieux/<slug>.md      une fiche par lieu précis qui a quelque chose à venir, avec son type
                        (cinéma, théâtre, galerie… : voir _data/types_lieux.yml)
- _collectifs/<id>.md   une fiche par source (lieu, collectif, festival qui publie sa programmation)
- _artistes/<slug>.md   une fiche par artiste : _data/artistes.yml, plus les noms lus dans
                        les titres (« Rencontre avec Sonia Hanihina ») ; chacune a un rôle :
                        artiste, ou conférencier quand on le voit surtout en conférence ou rencontre
- _data/lieux.json      nom du lieu tel qu'écrit dans un événement → fiche, et coordonnées pour la carte
- _data/geo.json        coordonnées trouvées par OpenStreetMap (Nominatim), gardées d'un passage à l'autre

  python3 -m scrapers.pages            fiches + coordonnées des nouveaux lieux
  python3 -m scrapers.pages --sans-geo fiches seulement
"""
from __future__ import annotations

import argparse
import hashlib
import collections
import json
import re
import time
import unicodedata

import requests
import yaml

from .commun import RACINE, slug

LIEUX, COLLECTIFS, ARTISTES = RACINE / "_lieux", RACINE / "_collectifs", RACINE / "_artistes"
FICHIER_LIEUX, FICHIER_GEO = RACINE / "_data" / "lieux.json", RACINE / "_data" / "geo.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
GEO_PAR_PASSAGE = 25   # Nominatim demande 1 requête par seconde au plus : on y va doucement

# Même règle que _includes/lien-carte.html : pas de fiche pour « Tunis » ou « X et Y ».
_VAGUE = re.compile(r"^(?:tunis|tunisie|en ligne|online|tba|tbd|à venir|secret location|lieu à préciser)$|voir l'article|voir l'annonce|\bet\b| / |plusieurs", re.I)
# « Rencontre avec Sonia Hanihina », « Yoga with Judit » : 2 à 4 mots en capitales après avec/with.
_AVEC = re.compile(r"\b(?:[Aa]vec|[Ww]ith)\s+((?:[A-ZÀ-Ý][\w'’-]+)(?:\s+(?:[A-ZÀ-Ý][\w'’-]+|ben|bel|el|de|du)){1,3})")
_PAS_NOM = re.compile(r"^(?:Le|La|Les|Un|Une|Des|Vous|Nous|Papa|Maman)\b")


# Événement de parole : conférence, rencontre, débat… (titre ou catégorie).
_PAROLE = re.compile(r"conf[ée]rence|rencontre|d[ée]bat|table[- ]ronde|colloque|s[ée]minaire|journ[ée]e d'[ée]tude|"
                     r"pr[ée]sentation (?:du|de son) (?:livre|roman|ouvrage)|signature|\btalk\b|panel|lecture|caf[ée] philo|causerie|"
                     r"محاضرة|ندوة|لقاء|حوار", re.I)
CATEGORIES_PAROLE = {"conference", "litterature"}
ROLES = ("artiste", "conferencier")


def _cle(texte: str) -> str:
    t = unicodedata.normalize("NFKD", (texte or "").replace("’", "'")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _slug(nom: str) -> str:
    """Slug lisible ; pour un nom en arabe (rien de latin), un code stable."""
    s = slug(nom)[:60]
    return s if s != "evenement" else "lieu-" + hashlib.sha1(nom.encode()).hexdigest()[:8]


def evenements() -> list[dict]:
    res = []
    for f in sorted((RACINE / "_events").rglob("*.md")):
        m = re.match(r"^---\n(.*?)\n---", f.read_text(), re.S)
        if m:
            try:
                e = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                continue
            res.append(e)
    return res


def _ecrire(fichier, champs: dict) -> None:
    lignes = ["---"] + [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in champs.items() if v not in (None, "", [])]
    texte = "\n".join(lignes + ["---", ""])
    if not fichier.exists() or fichier.read_text() != texte:
        fichier.write_text(texte)


GENRES_LIEU = {"lieu", "institution"}


def faux_lieux(sources: list[dict]) -> set[str]:
    """Noms qui ne sont pas des lieux : journaux, agendas, collectifs, festivals, délégations.

    Ces sources écrivent leur propre nom comme lieu quand une annonce n'en donne pas
    (« Kadhem », « Journées Cinématographiques de Carthage, Tunis »). Le lieu d'un festival
    qui a vraiment lieu quelque part (Fabrika : « One Resort, Monastir ») reste un lieu."""
    vrais, res = set(), set()
    for s in sources:
        nom = re.sub(r"\s*\((?:Instagram|Facebook|via [^)]*)\)$", "", s.get("nom") or "")
        lieu = (s.get("options") or {}).get("lieu") or ""
        if s.get("genre", "lieu") in GENRES_LIEU:
            vrais |= {_cle(nom), _cle(lieu), _cle(lieu.split(",")[0])}
            continue
        res |= {_cle(s.get("nom") or ""), _cle(nom)}
        premier = (_cle(nom).split() or [""])[0]
        if lieu and _cle(lieu).split()[:1] == [premier]:  # « Kadhem » pour la source Kadhem
            res |= {_cle(lieu), _cle(lieu.split(",")[0])}
    return res - vrais - {""}


def lieux(evts: list[dict], exclus: set[str] = frozenset()) -> dict[str, dict]:
    """Un lieu par nom normalisé : « Théâtre de l'Opéra » et « Theatre de l’Opera » ne font qu'un."""
    groupes: dict[str, dict] = {}
    alias = {_cle(k): v for k, v in (yaml.safe_load((RACINE / "_data" / "lieux_alias.yml").read_text()) or {}).items()}
    for e in evts:
        nom = str(e.get("venue") or "").strip()
        if not nom or _VAGUE.search(nom) or len(nom) > 90 or _cle(nom) in exclus:
            continue
        cible = alias.get(_cle(nom), nom)
        g = groupes.setdefault(_cle(cible), {"noms": collections.Counter(), "adresse": "", "ville": "", "n": 0, "nom": ""})
        if cible in alias.values():  # nom choisi dans lieux_alias.yml
            g["nom"] = cible
        g["noms"][nom] += 1
        g["adresse"] = g["adresse"] or str(e.get("address") or "")
        g["ville"] = g["ville"] or str(e.get("ville") or "tunis")
        g["n"] += 1
    return groupes


def references(groupes: dict[str, dict]) -> None:
    """Ajoute les lieux de _data/lieux_references.yml (listés même sans événement) et rattache
    leurs autres écritures : un événement « Goethe-Institut Tunis » ou « Institut Goethe » mène à la même fiche."""
    try:
        liste = yaml.safe_load((RACINE / "_data" / "lieux_references.yml").read_text()) or []
    except OSError:
        return
    for r in liste:
        nom = r["nom"]
        variantes = [nom, *(r.get("noms") or [])]
        # le groupe existe déjà sous l'une des écritures : on le garde et on lui donne le nom choisi
        existants = [k for k in dict.fromkeys(_cle(v) for v in variantes) if k and k in groupes]
        g = groupes.get(existants[0]) if existants else None
        if g is None:
            g = {"noms": collections.Counter(), "adresse": "", "ville": "", "n": 0, "nom": ""}
        for k in existants[1:]:  # deux groupes pour un même lieu : on les réunit
            autre = groupes.pop(k)
            g["noms"].update(autre["noms"])
            g["n"] += autre["n"]
            g["adresse"] = g["adresse"] or autre["adresse"]
            g["ville"] = g["ville"] or autre["ville"]
        for v in variantes:
            g["noms"][v] += 0  # connu, même sans événement : la fiche retrouve ses événements par ce nom
        g["nom"] = nom
        if r.get("type"):
            g["type"] = r["type"]
        g["adresse"] = g["adresse"] or r.get("adresse", "")
        g["ville"] = g["ville"] or r.get("ville", "tunis")
        if existants:
            groupes.pop(existants[0])
        groupes[_cle(nom)] = g


def _geocoder(requete: str) -> list[float] | None:
    r = requests.get(NOMINATIM, params={"q": requete, "format": "json", "limit": 1, "countrycodes": "tn"},
                     headers={"User-Agent": "agenda-nuit-tunis (https://github.com/benjello/agenda-nuit-tunis)"},
                     timeout=20)
    r.raise_for_status()
    res = r.json()
    return [round(float(res[0]["lat"]), 5), round(float(res[0]["lon"]), 5)] if res else None


def coordonnees(groupes: dict[str, dict], geo: dict, avec_reseau: bool) -> None:
    faits = 0
    for cle, g in sorted(groupes.items(), key=lambda kv: -kv[1]["n"]):
        nom = g["nom"] or g["noms"].most_common(1)[0][0]
        if cle in geo or not avec_reseau or faits >= GEO_PAR_PASSAGE:
            continue
        essais = [", ".join(x for x in (nom, g["adresse"]) if x), nom.split(",")[0]]
        geo[cle] = None
        for q in dict.fromkeys(essais):
            try:
                geo[cle] = _geocoder(q)
            except (requests.RequestException, ValueError, KeyError) as exc:
                print(f"  carte : {q} illisible ({exc.__class__.__name__})")
                del geo[cle]
                return  # réseau ou service indisponible : on réessaiera au prochain passage
            faits += 1
            time.sleep(1.1)
            if geo[cle]:
                break
    if faits:
        print(f"  carte : {faits} recherche(s) de lieu sur OpenStreetMap")


def types_lieux() -> dict:
    return yaml.safe_load((RACINE / "_data" / "types_lieux.yml").read_text()) or {}


def type_du_nom(nom: str, regles: list[dict]) -> str | None:
    """Type d'un lieu d'après son nom : « Cinéma Le Colisée » → cinema.

    La première règle qui convient l'emporte : « Salle de cinéma, Institut français » est un cinéma."""
    textes = (_cle(nom), (nom or "").lower())  # le second pour les noms en arabe
    for r in regles:
        if any(re.search(m, t) for m in r.get("mots") or [] for t in textes):
            return r["id"]
    return None


def type_lieu(nom: str, slug_: str, config: dict, osm: dict) -> str:
    """Type choisi à la main, sinon lu dans le nom, sinon l'étiquette OpenStreetMap, sinon « autre »."""
    manuels = {_cle(k): v for k, v in (config.get("lieux") or {}).items()}
    regles = config.get("types") or []
    connus = {r["id"] for r in regles}
    t = manuels.get(_cle(nom)) or type_du_nom(nom, regles) or (osm.get(f"lieu:{slug_}") or {}).get("type")
    return t if t in connus else "autre"


def _osm_lieux() -> dict:
    """Étiquettes OpenStreetMap gardées par scrapers/enrichir.py au passage précédent."""
    try:
        return json.loads((RACINE / "_data" / "enrichi.json").read_text()).get("osm") or {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ecrire_lieux(groupes: dict[str, dict], geo: dict) -> dict:
    LIEUX.mkdir(exist_ok=True)
    manuels = {_cle(k): v for k, v in (yaml.safe_load((RACINE / "_data" / "lieux_coords.yml").read_text()) or {}).items()}
    config, osm = types_lieux(), _osm_lieux()
    index, carte, fichiers = {}, [], set()
    for cle, g in groupes.items():
        nom = g["nom"] or g["noms"].most_common(1)[0][0]
        s = _slug(nom)
        point = manuels.get(cle) or geo.get(cle)
        fichier = LIEUX / f"{s}.md"
        fichiers.add(fichier.name)
        noms = sorted(g["noms"])
        t = type_lieu(nom, s, config, osm)
        if g.get("type") in {r["id"] for r in config.get("types") or []}:
            t = g["type"]  # type donné par _data/lieux_references.yml
        _ecrire(fichier, {"title": nom, "noms": noms, "type": t, "adresse": g["adresse"], "ville": g["ville"],
                          "lat": point[0] if point else None, "lon": point[1] if point else None})
        for n in noms:
            index[n] = s
        if point:
            carte.append({"slug": s, "nom": nom, "type": t, "ville": g["ville"], "lat": point[0], "lon": point[1],
                          "n": g["n"]})
    for f in LIEUX.glob("*.md"):
        if f.name not in fichiers:
            f.unlink()
    carte.sort(key=lambda x: -x["n"])
    return {"index": index, "carte": carte}


def ecrire_collectifs(evts: list[dict]) -> int:
    sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []
    actives = {e.get("source") for e in evts}
    COLLECTIFS.mkdir(exist_ok=True)
    gardes = {s["id"] for s in sources if s.get("actif", True) or s["id"] in actives}
    regroupees = {s["id"] for s in sources if s.get("fiche")}
    for f in COLLECTIFS.glob("*.md"):
        if f.stem not in gardes or f.stem in regroupees:
            f.unlink()
    # Plusieurs sources d'un même organisateur (site + Facebook…) : une seule fiche,
    # celle de la source nommée par « fiche: <id> » ; ses événements sont ceux de toutes.
    n, groupes = 0, {}
    for s in sources:
        if s["id"] in gardes:
            groupes.setdefault(s.get("fiche") or s["id"], []).append(s)
    for s in sources:
        if s["id"] not in gardes or s.get("fiche"):
            continue
        membres = sorted(groupes.get(s["id"], [s]), key=lambda m: m is not s)  # la source principale d'abord
        liens = []
        for m in membres:
            reseau = re.search(r"(instagram|facebook)\.com/([^/?#]+)", m.get("url", ""))
            liens.append({"reseau": reseau.group(1) if reseau else "site", "url": m.get("url")})
        _ecrire(COLLECTIFS / f"{s['id']}.md", {
            "title": s.get("nom_fiche") or s["nom"], "source": s["id"],
            "sources": [m["id"] for m in membres] if len(membres) > 1 else None,
            "type": s.get("type"), "url_source": s.get("url"),
            "reseau": liens[0]["reseau"] if liens[0]["reseau"] != "site" else None,
            "liens": liens if len(liens) > 1 else None,
            "categorie": s.get("categorie"), "genre": s.get("genre", "lieu")})
        n += 1
    return n


def artistes_des_titres(evts: list[dict]) -> dict[str, str]:
    """{slug: nom} des noms lus après « avec » dans les titres."""
    res = {}
    for e in evts:
        for nom in e.get("artists") or []:  # line-up donné par la source (Resident Advisor)
            nom = str(nom).strip()
            if 2 < len(nom) <= 60:
                res.setdefault(_slug(nom), nom)
        for m in _AVEC.finditer(str(e.get("title") or "")):
            nom = m.group(1).strip(" -’'")
            if not _PAS_NOM.match(nom):
                res.setdefault(_slug(nom), nom)
    return res


def de_parole(e: dict) -> bool:
    """Conférence, rencontre, débat : on y vient écouter quelqu'un parler."""
    return e.get("category") in CATEGORIES_PAROLE or bool(_PAROLE.search(str(e.get("title") or "")))


def role(mots: list[str], evts: list[dict]) -> str:
    """Conférencier si la moitié au moins de ses dates sont des conférences ou des rencontres.

    Même rattachement que la page (_layouts/artiste.html) : un des « mots » dans le titre ou le line-up."""
    parole = autres = 0
    for e in evts:
        t = f"{e.get('title') or ''} {' '.join(map(str, e.get('artists') or []))}".lower()
        if any(m in t for m in mots):
            if e.get("artists") and any(m in " ".join(map(str, e["artists"])).lower() for m in mots):
                autres += 1  # dans un line-up (Resident Advisor) : un artiste
            elif de_parole(e):
                parole += 1
            else:
                autres += 1
    return "conferencier" if parole and parole >= autres else "artiste"


def ecrire_artistes(evts: list[dict]) -> int:
    connus = yaml.safe_load((RACINE / "_data" / "artistes.yml").read_text()) or []
    ARTISTES.mkdir(exist_ok=True)
    fiches = {}
    for a in connus:
        fiches[slug(a["nom"])] = {"title": a["nom"], "mots": [m.lower() for m in a.get("mots") or [a["nom"]]],
                                  "role": a.get("role") if a.get("role") in ROLES else None,
                                  "instagram": a.get("instagram"), "facebook": a.get("facebook"),
                                  "site": a.get("site"), "genre": a.get("genre")}
    for s, nom in artistes_des_titres(evts).items():
        fiches.setdefault(s, {"title": nom, "mots": [nom.lower()]})
    for champs in fiches.values():
        champs["role"] = champs.get("role") or role(champs["mots"], evts)
    for f in ARTISTES.glob("*.md"):
        if f.stem not in fiches:
            f.unlink()
    for s, champs in fiches.items():
        _ecrire(ARTISTES / f"{s}.md", champs)
    return len(fiches)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sans-geo", action="store_true", help="ne pas chercher les coordonnées des lieux")
    args = p.parse_args(argv)
    evts = evenements()
    sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []
    groupes = lieux(evts, faux_lieux(sources))
    references(groupes)
    try:
        geo = json.loads(FICHIER_GEO.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        geo = {}
    coordonnees(groupes, geo, not args.sans_geo)
    FICHIER_GEO.write_text(json.dumps(geo, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    donnees = ecrire_lieux(groupes, geo)
    FICHIER_LIEUX.write_text(json.dumps(donnees, ensure_ascii=False, indent=1) + "\n")
    nc, na = ecrire_collectifs(evts), ecrire_artistes(evts)
    print(f"{len(groupes)} lieux ({len(donnees['carte'])} sur la carte), {nc} organisateurs, {na} artistes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
