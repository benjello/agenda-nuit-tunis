"""Repère les événements annoncés par plusieurs sources (ex. El Teatro et Teskerti).

Deux événements sont considérés comme le même :
- s'ils commencent au même moment dans le même lieu (sans heure, il faut en plus que
  le titre commence pareil) ;
- ou s'ils ont lieu le même jour, dans le même lieu écrit autrement (« Institut français
  de Tunis » / « L'Institut Français de Tunisie »), avec des titres proches : la moitié
  des mots du titre le plus court se retrouvent dans l'autre (« Festival du podcast » /
  « Podcast Days by Tunisia Podcast Festival ») ;
- ou, quand l'un des deux est un article de presse, si leurs dates se chevauchent (exposition
  du 27 octobre au 27 novembre, article du 31) dans le même lieu, avec des titres proches ;
- ou, quand une source ne donne pas de lieu précis (presse : « Tunisie, voir l'article »),
  le même jour avec des titres presque identiques (8 mots sur 10, 2 mots au moins).
Les films ne sont pas concernés : ils sont regroupés par titre ailleurs (films.py). On garde celui de la source la plus proche du lieu (le site du
lieu avant une billetterie, une billetterie avant un agrégateur) ; les autres sont
marqués « doublon » et ne s'affichent pas, mais leur lien est ajouté à l'événement
gardé (« Aussi sur : Teskerti »). Un article de presse n'est pas perdu : il passe dans la
liste « presse » de l'événement gardé (section « Dans la presse » de la fiche).

Lancé automatiquement à la fin de « python3 -m scrapers ».
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import yaml

from .commun import slug
from .ecriture import DOSSIER_AUTO, _yaml

PRIORITE = {"lieu": 0, "cinema": 0, "billetterie": 1, "agenda": 2}
_FM = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)


def _lire(f: Path):
    m = _FM.match(f.read_text())
    if not m:
        return None, ""
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def _ecrire(f: Path, champs: dict, corps: str):
    lignes = ["---"]
    for k, v in champs.items():
        if k == "date":
            lignes.append(f"date: {v}")
        else:
            lignes.append(f"{k}: {_yaml(v)}")
    f.write_text("\n".join(lignes + ["---", corps]).rstrip("\n") + "\n")


def _cle_lieu(lieu: str) -> str:
    # « El Teatro التياترو » et « El Teatro » → « el-teatro »
    return slug(lieu)[:12]


_ARTICLES = re.compile(r"^(?:l|le|la|les|el|al|the) ")
_VAGUE = re.compile(r"^(?:tunis|tunisie|en ligne|online|tba|tbd|a venir|lieu a preciser|lieu a definir)$|voir l.article|voir l.annonce|plusieurs")
_VIDES = {"les", "des", "une", "avec", "pour", "the", "and", "dans", "sur", "par", "aux", "est", "vous",
          "cinema", "concert", "spectacle", "soiree", "exposition", "rencontre", "atelier", "theatre", "with"}


def _norm(texte: str) -> str:
    t = unicodedata.normalize("NFKD", str(texte or "").replace("’", "'")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def _lieu_proche(lieu: str, alias: dict) -> str:
    """« L'Institut Français de Tunisie, Tunis » → « institut fra » ; vide si le lieu est vague."""
    brut = str(alias.get(_norm(lieu), lieu) or "")
    if not _norm(brut) or _VAGUE.search(_norm(brut)):
        return ""
    return _ARTICLES.sub("", _norm(brut.split(",")[0]))[:12]


def mots(titre: str) -> set[str]:
    return {m for m in re.findall(r"[a-z0-9]{3,}", _norm(titre)) if m not in _VIDES} | \
           set(re.findall(r"[\u0600-\u06ff]{3,}", str(titre or "")))


def proches(a: set, b: set, seuil: float, minimum: int = 1) -> bool:
    if not a or not b:
        return False
    commun = len(a & b)
    return commun >= minimum and commun / min(len(a), len(b)) >= seuil


def _titre_dans_texte(officiel: dict, article: tuple) -> bool:
    """Le titre de l'événement officiel est cité dans le texte de l'article
    (titre d'article générique : « À l'Institut français de Tunis », texte : « l'exposition Images de Syrie… »)."""
    titre = _norm(officiel.get("title", ""))
    if len(titre.split()) < 2 or len(titre) < 12:
        return False
    return titre in _norm(article[2])


def _alias() -> dict:
    try:
        from .commun import RACINE
        brut = yaml.safe_load((RACINE / "_data" / "lieux_alias.yml").read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {_norm(k): v for k, v in brut.items()}


def marquer(sources: list[dict], dossier: Path = DOSSIER_AUTO, articles: list[dict] | None = None) -> int:
    types = {s["id"]: s.get("type", "agenda") for s in sources}
    presse = {s["id"] for s in sources if s.get("genre") == "presse"}
    if articles is None:  # articles qui n'ont pas donné d'événement (scrapers/critiques.py)
        from . import critiques
        articles = critiques.lire(critiques.FICHIER_EVENEMENTS) if dossier == DOSSIER_AUTO else []
    evts = []
    for f in sorted(dossier.glob("*/*.md")):
        champs, corps = _lire(f)
        if not champs:
            continue
        champs.pop("doublon", None)
        champs.pop("autres_sources", None)
        champs.pop("presse", None)
        if not isinstance(champs.get("date"), str):
            champs["date"] = str(champs.get("date"))[:16]
        evts.append((f, champs, corps))
    # Les événements écrits à la main (_events/manuel) passent avant : on ne les modifie pas,
    # mais une annonce automatique du même événement est masquée.
    for f in sorted((dossier.parent / "manuel").glob("*.md")):
        champs, _ = _lire(f)
        if champs and champs.get("date"):
            champs["date"] = str(champs["date"])[:16]
            champs["_manuel"] = True
            evts.append((None, champs, ""))
    # 1. même moment, même lieu (règle d'origine)
    parent = list(range(len(evts)))

    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def unir(i, j):
        if evts[i][1].get("source") != evts[j][1].get("source"):
            parent[racine(j)] = racine(i)

    premiers: dict[tuple, int] = {}
    for i, e in enumerate(evts):
        c = e[1]
        date = str(c["date"])[:16]
        cle = (date, _cle_lieu(c.get("venue", "")))
        if len(date) <= 10 or date.endswith("00:00"):
            cle += (slug(str(c.get("title", "")))[:8],)
        if cle in premiers:
            unir(premiers[cle], i)
        else:
            premiers[cle] = i
    # 2. même jour, titres proches (lieu écrit autrement, ou pas de lieu précis)
    alias = _alias()
    par_jour: dict[str, list] = {}
    for i, e in enumerate(evts):
        if not e[1].get("film"):
            par_jour.setdefault(str(e[1]["date"])[:10], []).append(
                (i, _lieu_proche(e[1].get("venue", ""), alias), mots(e[1].get("title", ""))))
    for jour in par_jour.values():
        for x, (i, li, mi) in enumerate(jour):
            for j, lj, mj in jour[x + 1:]:
                if li and li == lj and proches(mi, mj, 0.5):
                    unir(i, j)
                elif (not li or not lj) and proches(mi, mj, 0.8, 2):
                    unir(i, j)
    # 3. un article de presse dont la période recoupe celle d'un événement du même lieu
    def periode(c):
        debut = str(c["date"])[:10]
        return debut, max(debut, str(c.get("end_date") or debut)[:10])

    for x, ei in enumerate(evts):
        for j, ej in enumerate(evts[:x]):
            ci, cj = ei[1], ej[1]
            if (ci.get("source") in presse) == (cj.get("source") in presse) or ci.get("film") or cj.get("film"):
                continue
            (d1, f1), (d2, f2) = periode(ci), periode(cj)
            li, lj = _lieu_proche(ci.get("venue", ""), alias), _lieu_proche(cj.get("venue", ""), alias)
            if d1 <= f2 and d2 <= f1 and (li == lj if (li and lj) else True) and \
                    (proches(mots(ci.get("title", "")), mots(cj.get("title", "")), 0.5 if (li and lj) else 0.8, 2)
                     or (li and li == lj and _titre_dans_texte(*((cj, ei) if ci.get("source") in presse else (ci, ej))))):
                unir(j, x)
    groupes: dict[int, list] = {}
    for i, e in enumerate(evts):
        groupes.setdefault(racine(i), []).append(e)
    n = 0
    for groupe in groupes.values():
        # la source la plus proche du lieu, puis celle qui donne une heure et un lieu précis
        groupe.sort(key=lambda e: (not e[1].get("_manuel"), e[1].get("source") in presse, PRIORITE.get(types.get(e[1].get("source")), 3),
                                   str(e[1]["date"]).endswith("00:00") or len(str(e[1]["date"])) <= 10,
                                   not _lieu_proche(e[1].get("venue", ""), alias), e[1].get("source", "")))
        garde = groupe[0]
        autres = [e for e in groupe[1:] if e[1].get("source") != garde[1].get("source")]
        # Un article de presse en doublon d'un événement officiel : masqué, mais son lien est gardé
        # dans « presse » (section de la fiche). Entre deux articles, c'est un doublon ordinaire.
        en_presse = [e for e in autres if e[1].get("source") in presse] if garde[1].get("source") not in presse else []
        if en_presse:
            autres = [e for e in autres if e not in en_presse]
            if garde[0] is not None:
                garde[1]["presse"] = [{"titre": e[1].get("article_titre") or e[1].get("title"), "lien": e[1].get("link"),
                                       "source_nom": e[1].get("source_name"), "date": e[1].get("ajoute")}
                                      for e in en_presse]
            for e in en_presse:
                e[1]["doublon"] = True
                n += 1
        if autres and garde[0] is None:  # gardé : l'événement écrit à la main
            for e in autres:
                if e[0] is not None:
                    e[1]["doublon"] = True
                    n += 1
        elif autres:
            vus = {}
            for e in autres:
                vus.setdefault(e[1].get("source"), e)
            garde[1]["autres_sources"] = [{"name": e[1].get("source_name"), "link": e[1].get("link"), "source": e[1].get("source")} for e in vus.values()]
            for e in autres:
                e[1]["doublon"] = True
                n += 1
    # 4. articles sans événement propre : rattachés à la manifestation officielle qu'ils couvrent
    #    (dates qui se chevauchent, titre proche, même lieu s'il est connu)
    for a in articles:
        debut, fin = a.get("debut", ""), a.get("fin") or a.get("debut", "")
        if not debut:
            continue
        for f, c, _ in evts:
            if f is None or c.get("doublon") or c.get("source") in presse or c.get("film"):
                continue
            d2, f2 = periode(c)
            lieu_a = _lieu_proche(a.get("lieu", ""), alias)
            if debut <= f2 and d2 <= fin and (not lieu_a or lieu_a == _lieu_proche(c.get("venue", ""), alias)) and \
                    (proches(mots(a.get("evenement", "")), mots(c.get("title", "")), 0.5, 2)
                     or proches(mots(a.get("titre", "")), mots(c.get("title", "")), 0.8, 2)):
                liste = c.setdefault("presse", [])
                if all(x.get("lien") != a["lien"] for x in liste):
                    liste.append({"titre": a["titre"], "lien": a["lien"], "source_nom": a.get("source_nom"), "date": a.get("date")})
    for f, champs, corps in evts:
        if f is None:
            continue
        # « auto: true » en dernier, comme à l'écriture
        auto = champs.pop("auto", True)
        champs["auto"] = auto
        _ecrire(f, champs, corps)
    return n
