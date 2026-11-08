"""Granularité des événements : chaque entrée doit être un événement précis.

Un film doit être un vrai film (son titre, ses séances), une expo une vraie expo (son nom,
ses dates), avec un lien vers sa propre fiche, pas vers la page générale d'un institut,
un programme PDF du mois ou l'accueil d'un site.

Ce module relit les événements écrits par les scrapers et dit, pour chacun, ce qui manque.
Le contrôle (scrapers/controle.py) l'appelle après chaque passage : le bilan par source et
par type de scraper va dans _data/controle.json et s'affiche sur la page « Santé des sources ».

  python3 -m scrapers.granularite     # bilan dans le terminal
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

from .commun import RACINE, pas_un_evenement, slug, titre_film, titre_generique

# Défauts qui font qu'une entrée n'est pas un événement précis. L'ordre est celui de l'affichage.
DEFAUTS = {
    "pas_evenement": "annonce de service, pas un événement",
    "titre_generique": "titre générique (genre ou rubrique, pas le nom de l'œuvre)",
    "titre_phrase": "titre = phrase d'annonce ou d'article, pas le nom de l'événement",
    "titre_prefixe": "rubrique devant le titre du film",
    "lien_general": "lien vers une page générale (programme, PDF, accueil), pas une fiche",
    "lien_partage": "même lien pour plusieurs événements différents",
    "film_sans_seance": "film sans horaire ni séance",
    "expo_sans_fin": "expo sans date de fin",
    "lieu_vague": "lieu à préciser",
}
# Ce qui manque sans rendre l'entrée fausse : compté par source, pas signalé un par un.
MANQUES = {
    "sans_heure": "heure",
    "sans_image": "image",
    "sans_notice": "notice",
}
# Défauts signalés un par un dans « Entrées à vérifier » (les autres ne sont que comptés par source,
# sinon un programme PDF de 60 cases remplirait la liste).
A_SIGNALER = ("pas_evenement", "titre_generique", "titre_phrase", "titre_prefixe", "film_sans_seance")

# Pages générales : programme, agenda, rubrique, accueil.
_CHEMIN_GENERAL = re.compile(r"(?:^|/)(?:list-)?(?:agenda|programmes?|programmation|evenements?|events|cinema|"
                             r"films?|expositions?|category|categorie|feed|calendrier|accueil|home|index\.\w+)/?$", re.I)
_RESEAUX = re.compile(r"(?:^|\.)(?:facebook\.com|instagram\.com|fb\.com)$", re.I)
_PUBLICATION = re.compile(r"/(?:posts|p|reel|events|photos?|videos?|permalink)[/.]|story_fbid|/share/", re.I)

# Phrase d'annonce ou titre d'article : « Cinéma : Le Temps suspendu, un film hongrois à ne pas rater »,
# « Podcast Days … vous dévoile son programme », « Tunisie | Entrée gratuite… ».
_PHRASE = re.compile(r"\bvous (?:d[ée]voile|invite|attend|propose|donne|pr[ée]sente)\b|\b[àa] ne pas (?:rater|manquer)\b|"
                     r"\blorsque\b|\bd[ée]couvrez\b|\bne ratez pas\b|\bvenez\b|\bje vous\b|\bnous vous\b|"
                     r"يدعوكم|ندعوكم|يسعدنا|في إطار فعاليات", re.I)
_RUBRIQUE = re.compile(r"^(?:Tunisie|Culture|Cin[ée]ma|Th[ée][âa]tre|Musique|Expo(?:sition)?|Festival|Livres?|Agenda|"
                       r"Sortie|Critique|Interview|Portrait|Entretien)\s*[:|]\s", re.I)


def _heure(date: str) -> bool:
    return bool(re.search(r"\d{1,2}:\d{2}", date)) and not re.search(r"\b00:00\b", date)


def lien_general(lien: str, source_url: str = "") -> bool:
    """Vrai si le lien mène à une page générale (programme, PDF, accueil, profil) et pas à une fiche."""
    if not lien:
        return True
    u = urlparse(lien)
    chemin = unquote(u.path or "")
    if source_url and lien.rstrip("/") == source_url.rstrip("/"):
        return True
    if chemin.lower().endswith(".pdf") or chemin.strip("/") == "":
        return True
    if _RESEAUX.search(u.netloc or "") and not _PUBLICATION.search(chemin + "?" + (u.query or "")):
        return True  # profil d'une page, pas une publication
    return bool(_CHEMIN_GENERAL.search(chemin))


def defauts(champs: dict, corps: str = "", source: dict | None = None, partages: set | None = None) -> list[str]:
    """Codes des défauts d'une entrée (voir DEFAUTS et MANQUES)."""
    source = source or {}
    titre = str(champs.get("title") or "").strip()
    categorie = champs.get("category") or ""
    date = str(champs.get("date") or "")
    res = []
    if pas_un_evenement(titre):
        res.append("pas_evenement")
    if titre_generique(titre):
        res.append("titre_generique")
    elif _PHRASE.search(titre) or _RUBRIQUE.search(titre) or (
            source.get("genre") == "presse" and re.search(r"\w{3,}\s*:\s+\S", titre) and len(titre) > 45):
        res.append("titre_phrase")
    if (categorie == "cinema" or champs.get("film")) and titre_film(titre) != titre:
        res.append("titre_prefixe")
    lien = str(champs.get("link") or "")
    if lien_general(lien, source.get("url", "")):
        res.append("lien_general")
    elif partages and lien in partages:
        res.append("lien_partage")
    if champs.get("film") and not champs.get("seances") and not _heure(date):
        res.append("film_sans_seance")
    if categorie == "expo" and not champs.get("end_date"):
        res.append("expo_sans_fin")
    lieu = str(champs.get("venue") or "")
    if not lieu or re.search(r"à préciser|voir l.(?:annonce|article)", lieu, re.I):
        res.append("lieu_vague")
    if not _heure(date) and not champs.get("end_date") and not champs.get("seances") and categorie != "expo":
        res.append("sans_heure")
    if not champs.get("image"):
        res.append("sans_image")
    if len(corps.strip()) < 40:
        res.append("sans_notice")
    return res


def liens_partages(entrees: list[dict]) -> set[str]:
    """Liens qui servent à plusieurs événements de titres différents dans une même source
    (un film dans plusieurs salles garde un seul lien : ce n'est pas un défaut)."""
    titres = defaultdict(set)
    for c in entrees:
        titres[str(c.get("link") or "")].add(slug(str(c.get("title") or ""))[:25])
    return {l for l, t in titres.items() if l and len(t) > 1}


def _vide():
    return {"n": 0, "precis": 0, "defauts": Counter(), "manques": Counter(), "exemples": {}}


def _ajouter(b: dict, codes: list[str], titre: str):
    b["n"] += 1
    graves = [c for c in codes if c in DEFAUTS]
    if not graves:
        b["precis"] += 1
    for c in codes:
        (b["defauts"] if c in DEFAUTS else b["manques"])[c] += 1
        if c in DEFAUTS:
            b["exemples"].setdefault(c, titre[:70])


def _resume(b: dict) -> dict:
    n = b["n"]
    return {
        "n": n,
        "precis": b["precis"],
        "pourcent": round(100 * b["precis"] / n) if n else None,
        "defauts": [{"code": c, "texte": DEFAUTS[c], "n": b["defauts"][c], "exemple": b["exemples"].get(c, "")}
                    for c in DEFAUTS if b["defauts"][c]],
        "manques": [{"code": c, "texte": MANQUES[c], "n": b["manques"][c]} for c in MANQUES if b["manques"][c]],
    }


def bilan(entrees: list[tuple[dict, str]], sources: list[dict]) -> dict:
    """Bilan par source et par type de scraper.

    entrees : (champs, corps) des événements, sans les doublons."""
    par_id = {s["id"]: s for s in sources}
    par_source = defaultdict(list)
    for champs, corps in entrees:
        par_source[champs.get("source")].append((champs, corps))
    sources_b, scrapers_b, evenements = {}, defaultdict(_vide), {}
    for sid, liste in par_source.items():
        src = par_id.get(sid, {})
        partages = liens_partages([c for c, _ in liste])
        b = _vide()
        for champs, corps in liste:
            codes = defauts(champs, corps, src, partages)
            titre = str(champs.get("title") or "")
            _ajouter(b, codes, titre)
            _ajouter(scrapers_b[src.get("scraper", "?")], codes, titre)
            evenements[(sid, champs.get("_fichier"))] = codes
        sources_b[sid] = _resume(b)
    types = {k: _resume(v) for k, v in scrapers_b.items()}
    return {"sources": sources_b,
            "scrapers": dict(sorted(types.items(), key=lambda kv: (kv[1]["pourcent"] or 0, -kv[1]["n"]))),
            "evenements": evenements}


def main() -> int:
    from .doublons import _lire
    from .ecriture import DOSSIER_AUTO
    sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []
    entrees = []
    for f in sorted(Path(DOSSIER_AUTO).glob("*/*.md")):
        champs, corps = _lire(f)
        if champs and not champs.get("doublon"):
            entrees.append((champs, corps or ""))
    b = bilan(entrees, sources)
    print("Par type de scraper (part d'événements précis) :")
    for k, v in b["scrapers"].items():
        print(f"  {k:22} {v['pourcent']:>3} % de {v['n']:>3}  " +
              " ; ".join(f"{d['texte']} ×{d['n']}" for d in v["defauts"]))
    print("\nPar source :")
    for k, v in sorted(b["sources"].items(), key=lambda kv: kv[1]["pourcent"] or 0):
        print(f"  {k:24} {v['pourcent']:>3} % de {v['n']:>3}  " +
              " ; ".join(f"{d['code']} ×{d['n']}" for d in v["defauts"]) +
              ("  | manque : " + ", ".join(f"{m['texte']} ×{m['n']}" for m in v["manques"]) if v["manques"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
