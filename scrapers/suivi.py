"""Suivi des pannes : une issue GitHub par source en panne, ouverte, mise à jour et fermée seule.

Une source est « en panne » quand sa dernière lecture a échoué (erreur, pas simple attente) et
qu'elle a raté deux passages quotidiens de suite : une coupure réseau d'un seul passage ne
déclenche rien. Chaque panne a son issue « Source en panne : <id> » (étiquettes `alerte` et
`panne`), pour qu'une PR de correction puisse écrire « Closes #N ». Quand la source relit sans
erreur (ou est mise en pause), le script ferme l'issue avec un commentaire.

Les sources silencieuses (lues sans erreur mais muettes) restent dans l'issue commune
« Sources silencieuses » (`scrapers/alerte.py`).

  python3 -m scrapers.suivi            # synchronise les issues (gh et GH_TOKEN nécessaires)
  python3 -m scrapers.suivi --rapport  # affiche seulement la liste des pannes
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

import yaml

from .commun import RACINE
from .ecriture import lire_etat

PREFIXE = "Source en panne : "
DELAI = dt.timedelta(hours=36)  # deux passages quotidiens ratés de suite


def pannes(sources: list[dict], etat: dict) -> list[tuple[dict, dict]]:
    """(source, état) pour chaque source active dont la lecture échoue depuis au moins DELAI."""
    res = []
    for s in sources:
        if not s.get("actif", True):
            continue
        e = etat.get(s["id"]) or {}
        if e.get("ok") is not False or not e.get("dernier_passage"):
            continue
        succes = e.get("dernier_succes")
        if succes and dt.datetime.fromisoformat(e["dernier_passage"]) - dt.datetime.fromisoformat(succes) < DELAI:
            continue
        res.append((s, e))
    return res


def corps(s: dict, e: dict) -> str:
    depot = os.environ.get("GITHUB_REPOSITORY", "benjello/agenda-nuit-tunis")
    return "\n".join([
        f"La source **{s['nom']}** (`{s['id']}`, scraper `{s.get('scraper', '?')}`) ne se lit plus.",
        "",
        f"- Page lue : {s.get('url') or '—'}",
        f"- Dernière lecture réussie : {(e.get('dernier_succes') or 'jamais')[:16].replace('T', ' ')}",
        f"- Dernière tentative : {e['dernier_passage'][:16].replace('T', ' ')}",
        f"- Dernière annonce trouvée : {(e.get('dernier_non_vide') or 'jamais')[:10]}",
        "",
        "Erreur :",
        "```",
        (e.get("erreur") or "?").replace("```", "'''"),
        "```",
        "",
        "Pour mettre au point : Actions → Scrapers → Run workflow, avec cet id dans « sources » et "
        "« debug » coché (les pages téléchargées sont gardées en artefact). Sur un ordinateur : "
        f"`python3 -m scrapers {s['id']} --debug`.",
        f"Voir aussi la [page Santé](https://{depot.split('/')[0]}.github.io/{depot.split('/')[-1]}/sante/).",
        "",
        "Cette issue est mise à jour chaque jour par le workflow des scrapers, et fermée quand la source relit sans erreur.",
    ])


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def synchroniser(liste: list[tuple[dict, dict]], appel=gh) -> list[str]:
    """Ouvre, met à jour ou ferme les issues « Source en panne ». Renvoie ce qui a été fait."""
    ouvertes = json.loads(appel("issue", "list", "--state", "open", "--label", "panne",
                                "--limit", "200", "--json", "number,title") or "[]")
    par_id = {i["title"][len(PREFIXE):].strip(): i["number"] for i in ouvertes if i["title"].startswith(PREFIXE)}
    fait = []
    if liste and not par_id:
        for nom, couleur in (("alerte", "B5442F"), ("panne", "D93F0B")):
            try:
                appel("label", "create", nom, "--color", couleur, "--force")
            except subprocess.CalledProcessError:
                pass
    en_panne = set()
    for s, e in liste:
        en_panne.add(s["id"])
        if s["id"] in par_id:
            appel("issue", "edit", str(par_id[s["id"]]), "--body", corps(s, e))
            fait.append(f"mise à jour #{par_id[s['id']]} ({s['id']})")
        else:
            appel("issue", "create", "--title", PREFIXE + s["id"], "--label", "alerte", "--label", "panne",
                  "--body", corps(s, e))
            fait.append(f"ouverte ({s['id']})")
    for sid, num in par_id.items():
        if sid not in en_panne:
            appel("issue", "close", str(num), "--comment",
                  f"`{sid}` se relit sans erreur (ou a été mise en pause) : issue fermée automatiquement.")
            fait.append(f"fermée #{num} ({sid})")
    return fait


def main(argv: list[str]) -> int:
    sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []
    liste = pannes(sources, lire_etat())
    for s, e in liste:
        print(f"✗ {s['id']} : {(e.get('erreur') or '')[:120]}")
    if not liste:
        print("Aucune source en panne.")
    if "--rapport" in argv:
        return 0
    for ligne in synchroniser(liste):
        print(ligne)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
