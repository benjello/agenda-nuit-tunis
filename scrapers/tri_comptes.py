"""Ticket GitHub « Tri des comptes repérés par les hashtags » : on y coche les faux positifs.

Chaque compte proposé (_data/comptes_proposes.json) est une case à cocher du ticket (étiquette « tri-comptes »).
Une case cochée = un faux positif : le compte part dans _data/comptes_exclus.yml et n'est plus jamais proposé.

  python3 -m scrapers.tri_comptes lire     # cases cochées → comptes_exclus.yml (à chaque modification du ticket)
  python3 -m scrapers.tri_comptes ecrire   # lire, puis réécrire le ticket avec les comptes proposés (chaque lundi)

Variables : GITHUB_REPOSITORY et GITHUB_TOKEN (fournies par GitHub Actions).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

import yaml

from .recherche_hashtags import EXCLUS, FICHIER, exclus

ETIQUETTE = "tri-comptes"
TITRE = "Tri des comptes repérés par les hashtags"
COCHEE = re.compile(r"(?im)^\s*[-*]\s*\[x\]\s*@([\w.]+)")
ENTETE = """Comptes Instagram qui publient des affiches de soirée sous les hashtags de la nuit, après un premier tri \
automatique (immobilier, voyages, hôtels, boutiques et comptes inactifs depuis 4 mois déjà retirés).

**Cochez les faux positifs** (ce n'est pas un lieu, un collectif ou un organisateur de soirées). Ils sont retirés \
de la page Contribuer et ne seront plus proposés. Les cases non cochées restent « à vérifier ».

Liste refaite chaque lundi par le workflow « Recherche de comptes par hashtags ».
"""


def cochees(corps: str) -> set[str]:
    return {c.lower() for c in COCHEE.findall(corps or "")}


def corps_du_ticket(comptes: list[dict], lu_le: str) -> str:
    lignes = [ENTETE, f"_Lecture du {lu_le} : {len(comptes)} compte(s)._", ""]
    for c in comptes:
        nom = f" · {c['nom']}" if c.get("nom") else ""
        exemple = f" · [dernière]({c['exemple']})" if c.get("exemple") else ""
        lignes.append(f"- [ ] @{c['compte']}{nom} · {c['soirees']} affiche(s) · {c.get('derniere', '')}{exemple}")
    return "\n".join(lignes) + "\n"


def ajouter_exclus(nouveaux: set[str]) -> set[str]:
    """Ajoute les comptes à comptes_exclus.yml ; renvoie ceux qui n'y étaient pas."""
    deja = exclus()
    ajout = nouveaux - deja
    if ajout:
        EXCLUS.write_text("# Faux positifs de la recherche par hashtags (cochés dans le ticket « tri-comptes »).\n"
                          + yaml.safe_dump(sorted(deja | ajout), allow_unicode=True))
    return ajout


def _api(chemin: str, methode: str = "GET", donnees: dict | None = None):
    depot, jeton = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(f"https://api.github.com/repos/{depot}/{chemin}", method=methode,
                                 data=json.dumps(donnees).encode() if donnees else None,
                                 headers={"Authorization": f"Bearer {jeton}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or "null")


def ticket() -> dict | None:
    tickets = _api(f"issues?labels={ETIQUETTE}&state=open&per_page=5")
    return tickets[0] if tickets else None


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not os.environ.get("GITHUB_TOKEN"):
        print("GITHUB_TOKEN manquant")
        return 1
    t = ticket()
    ajout = ajouter_exclus(cochees(t["body"])) if t else set()
    print(f"tri comptes : {len(ajout)} faux positif(s) ajouté(s) : {', '.join(sorted(ajout)) or '-'}")
    donnees = json.loads(FICHIER.read_text())
    ecartes = exclus()
    if ajout:  # retirés tout de suite de la page Contribuer
        donnees["comptes"] = [c for c in donnees["comptes"] if c["compte"] not in ecartes]
        FICHIER.write_text(json.dumps(donnees, ensure_ascii=False, indent=1))
    if argv[:1] == ["ecrire"]:
        comptes = [c for c in donnees["comptes"] if not c.get("suivi")]
        corps = corps_du_ticket(comptes, donnees.get("lu_le", ""))
        if t:
            _api(f"issues/{t['number']}", "PATCH", {"body": corps})
        else:
            t = _api("issues", "POST", {"title": TITRE, "body": corps, "labels": [ETIQUETTE]})
        print(f"tri comptes : ticket #{t['number']} à jour ({len(comptes)} compte(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
