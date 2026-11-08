"""Archive les événements passés avant que les scrapers ne les effacent.

Chaque passage des scrapers réécrit _events/auto/ et n'y garde que ce qui est à venir.
Ce script, lancé juste avant, recopie les événements terminés dans archives/donnees/AAAA.json
(un fichier par année, lu par la page /archives/ pour la recherche).

  python3 -m scrapers.archives              # archive ce qui est passé dans _events/
  python3 -m scrapers.archives --depuis-git # rattrape aussi les fichiers effacés dans l'historique git
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys

import yaml

from .commun import RACINE, propre

DOSSIER = RACINE / "archives" / "donnees"
RESUME = 240  # caractères de la notice gardés pour la recherche


def _lire(texte: str, chemin: str) -> dict | None:
    """Front matter + début de la notice → entrée d'archive, ou None si illisible."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", texte, re.S)
    if not m:
        return None
    try:
        tete = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not tete.get("title") or not tete.get("date") or tete.get("doublon") or tete.get("film"):
        return None
    debut = tete["date"]
    fin = tete.get("end_date") or debut
    heure = debut.strftime("%H:%M") if isinstance(debut, dt.datetime) else ""
    entree = {
        "titre": propre(str(tete["title"])),
        "debut": str(debut)[:10],
        "fin": str(fin)[:10],
        "heure": "" if heure == "00:00" else heure,
        "lieu": propre(str(tete.get("venue") or "")),
        "ville": tete.get("ville") or "",
        "categorie": tete.get("category") or "autre",
        "lien": tete.get("link") or "",
        "source": tete.get("source_name") or tete.get("source") or "",
        "resume": propre(re.sub(r"<[^>]+>|[#*_>\[\]]", " ", m.group(2)))[:RESUME],
        "fichier": chemin,
    }
    return entree


def _cle(e: dict) -> str:
    return f"{e['debut']}|{e['lieu'].lower()}|{e['titre'].lower()[:60]}"


def _charger() -> dict[str, dict[str, dict]]:
    annees = {}
    for f in DOSSIER.glob("[0-9][0-9][0-9][0-9].json"):  # pas index.json (le décompte par année)
        liste = json.loads(f.read_text())
        annees[f.stem] = {_cle(e): e for e in liste}
    return annees


def _ajouter(annees: dict, e: dict, aujourd_hui: str) -> bool:
    if e["fin"] >= aujourd_hui:
        return False
    a = annees.setdefault(e["debut"][:4], {})
    k = _cle(e)
    if k in a:
        return False
    a[k] = e
    return True


def _depuis_git(annees: dict, aujourd_hui: str) -> int:
    """Fichiers d'événement effacés au fil des commits : on relit leur dernière version."""
    r = subprocess.run(["git", "log", "--diff-filter=D", "--name-only", "--format=@%H", "--", "_events"],
                       cwd=RACINE, capture_output=True, text=True, check=True)
    n, commit = 0, ""
    for ligne in r.stdout.splitlines():
        if ligne.startswith("@"):
            commit = ligne[1:]
        elif ligne.endswith(".md") and commit:
            s = subprocess.run(["git", "show", f"{commit}^:{ligne}"], cwd=RACINE, capture_output=True, text=True)
            e = _lire(s.stdout, ligne) if s.returncode == 0 else None
            n += bool(e and _ajouter(annees, e, aujourd_hui))
    return n


def archiver(depuis_git: bool = False) -> int:
    aujourd_hui = dt.date.today().isoformat()
    annees = _charger()
    n = 0
    for f in sorted((RACINE / "_events").rglob("*.md")):
        if f.name == "README.md":
            continue
        e = _lire(f.read_text(), str(f.relative_to(RACINE)))
        n += bool(e and _ajouter(annees, e, aujourd_hui))
    if depuis_git:
        n += _depuis_git(annees, aujourd_hui)
    if n:
        DOSSIER.mkdir(parents=True, exist_ok=True)
        for annee, entrees in annees.items():
            liste = sorted(entrees.values(), key=lambda e: (e["debut"], e["heure"], e["titre"]))
            (DOSSIER / f"{annee}.json").write_text(json.dumps(liste, ensure_ascii=False, indent=0) + "\n")
    # Index des années, lu par la page /archives/
    DOSSIER.mkdir(parents=True, exist_ok=True)
    index = {a: len(e) for a, e in sorted(annees.items(), reverse=True)}
    (DOSSIER / "index.json").write_text(json.dumps(index) + "\n")
    print(f"archives : {n} événement(s) ajouté(s), {sum(index.values())} en tout")
    return n


if __name__ == "__main__":
    archiver(depuis_git="--depuis-git" in sys.argv)
