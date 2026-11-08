"""Transforme une proposition d'événement (issue GitHub validée) en fichier de l'agenda.

Lancé par le workflow « Proposition validée » quand l'étiquette « valide » est posée sur
une issue « Proposer un événement ». Lit le texte de l'issue dans la variable ISSUE_BODY,
écrit _events/propositions/<date>-<titre>.md et affiche le chemin du fichier.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys

from .commun import RACINE, slug
from .ecriture import _yaml

def _categories() -> dict[str, str]:
    """Libellé du formulaire (« Club », « Stand-up »…) ou clé → clé de _data/categories.yml."""
    import yaml
    cats = yaml.safe_load((RACINE / "_data" / "categories.yml").read_text()) or {}
    return {**{k: k for k in cats}, **{v["label"].lower(): k for k, v in cats.items()}}


CATEGORIES = _categories()
DOSSIER = RACINE / "_events" / "propositions"


def champs(corps: str) -> dict:
    """Les réponses d'un formulaire d'issue : « ### Titre\\n\\nvaleur »."""
    res = {}
    for bloc in re.split(r"^### ", corps, flags=re.M)[1:]:
        nom, _, valeur = bloc.partition("\n")
        valeur = valeur.strip()
        res[nom.strip().split(" (")[0].lower()] = "" if valeur == "_No response_" else valeur
    return res


def evenement(corps: str, numero: str = "") -> tuple[str, str]:
    """(nom de fichier, contenu Markdown). Lève ValueError si la date est illisible."""
    c = champs(corps)
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:[ T]+(\d{1,2})[:hH](\d{2}))?", c.get("date et heure", ""))
    if not m:
        raise ValueError(f"date illisible : {c.get('date et heure')!r} (attendu AAAA-MM-JJ HH:MM)")
    jour = dt.date.fromisoformat(m.group(1))
    date = f"{jour} {int(m.group(2)):02d}:{m.group(3)}" if m.group(2) else str(jour)
    titre = c.get("titre", "").strip() or "Événement"
    texte = c.get("description et affiche", "")
    image = re.search(r"https://(?:github\.com/user-attachments/assets|user-images\.githubusercontent\.com)/\S+?(?=[)\"\s]|$)", texte)
    lignes = ["---", f"title: {_yaml(titre)}", f"date: {date}"]
    fin = re.match(r"\d{4}-\d{2}-\d{2}", c.get("date de fin", ""))
    if fin:
        lignes.append(f"end_date: {fin.group(0)}")
    lignes += [f"venue: {_yaml(c.get('lieu', ''))}",
               f"category: {_yaml(CATEGORIES.get(c.get('catégorie', '').lower(), 'autre'))}"]
    if c.get("prix"):
        lignes.append(f"price: {_yaml(c['prix'])}")
    lignes += [f"link: {_yaml(c.get('lien', ''))}", 'source_name: "Proposé sur l\'agenda"']
    if image:
        lignes.append(f"image: {_yaml(image.group(0))}")
    if numero:
        lignes.append(f"proposition: {numero}")
    sans_image = re.sub(r"!\[[^\]]*\]\([^)]*\)|<img[^>]*>", "", texte).strip()
    contenu = "\n".join(lignes + ["---", sans_image]).rstrip() + "\n"
    return f"{jour}-{slug(titre)[:60]}.md", contenu


def main() -> int:
    nom, contenu = evenement(os.environ.get("ISSUE_BODY", ""), os.environ.get("ISSUE_NUMBER", ""))
    DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin = DOSSIER / nom
    chemin.write_text(contenu)
    print(chemin.relative_to(RACINE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
