"""« Ce qu'en dit la presse » : les articles de journaux sur les films à l'affiche.

Un article sur un film en salles (critique, sortie) ne devient pas un événement : les séances
viennent des cinémas. Le scraper presse le garde quand même ici, dans _data/critiques.json,
et scrapers/films.py le rattache au film qu'il nomme. La fiche de chaque séance de ce film
montre alors l'encadré « Ce qu'en dit la presse » avec les liens vers les articles.

Le fichier s'accumule d'un passage à l'autre (un flux RSS ne garde que les derniers articles),
et oublie les articles de plus de JOURS_GARDES jours.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path

from .commun import RACINE

FICHIER = RACINE / "_data" / "critiques.json"
FICHIER_EVENEMENTS = RACINE / "_data" / "presse.json"  # articles sur une manifestation (pas un film)
JOURS_GARDES = 180


def lire(fichier: Path = FICHIER) -> list[dict]:
    try:
        return json.loads(fichier.read_text())
    except (FileNotFoundError, ValueError):
        return []


def garder(nouveaux: list[dict], fichier: Path = FICHIER) -> int:
    """Ajoute les articles (clé : le lien), oublie les vieux. Rend le nombre d'articles gardés."""
    limite = (dt.date.today() - dt.timedelta(days=JOURS_GARDES)).isoformat()
    tous = {a["lien"]: a for a in lire(fichier)}
    for a in nouveaux:
        if a.get("lien"):
            tous[a["lien"]] = a
    garde = sorted((a for a in tous.values() if a.get("date", "") >= limite),
                   key=lambda a: (a.get("date", ""), a["lien"]), reverse=True)
    fichier.write_text(json.dumps(garde, ensure_ascii=False, indent=1) + "\n")
    return len(garde)


def _mots(texte: str) -> list[str]:
    t = unicodedata.normalize("NFKC", texte)
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", t).lower().split()


def parle_du_film(article: dict, titre_film: str) -> bool:
    """L'article nomme-t-il ce film ?
    - le nom tiré du titre de l'article (« Cinéma : Bakma, une comédie… » → « Bakma ») est le film ;
    - ou le titre de l'article contient le titre du film en entier, s'il a au moins deux mots
      (« Last Chance ») ou s'il est entre guillemets (« « Weekend » ») : un titre d'un seul mot
      courant (« Weekend ») sans guillemets serait trop souvent un faux ami."""
    from .films import morceaux
    cles = morceaux(titre_film)
    if not cles:
        return False
    if cles & morceaux(article.get("film", "")):
        return True
    titre = f" {' '.join(_mots(article.get('titre', '')))} "
    cites = {" ".join(_mots(c)) for c in re.findall(r"[«“\"]\s*([^»”\"]{2,80}?)\s*[»”\"]", article.get("titre", ""))}
    return any(f" {c} " in titre and (" " in c or c in cites) for c in cles)


def rattacher(films: list[dict], articles: list[dict] | None = None, n: int = 5) -> None:
    """Ajoute à chaque film « presse » : ses articles, du plus récent au plus ancien (n au plus)."""
    articles = lire() if articles is None else articles
    for f in films:
        trouves = [a for a in articles if parle_du_film(a, f["titre"])]
        trouves.sort(key=lambda a: a.get("date", ""), reverse=True)
        f["presse"] = [{k: a.get(k, "") for k in ("titre", "lien", "source_nom", "date")} for a in trouves[:n]]
