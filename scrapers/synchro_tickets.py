"""Synchro BACKLOG.md <-> issues GitHub ouvertes : signale les écarts, ne modifie rien.

  python3 -m scrapers.synchro_tickets

Deux écarts sont signalés :
- une issue ouverte que BACKLOG.md ne cite nulle part (ni `#N` ni `issues/N`) ;
- une case non cochée (« - [ ] ») sans aucun numéro d'issue sur sa ligne.

Dans GitHub Actions (variables GITHUB_REPOSITORY et GITHUB_TOKEN), le rapport est aussi
écrit dans le résumé du workflow. Sans jeton, le script affiche seulement le relevé local.
"""
import json
import os
import re
import urllib.request

from scrapers.commun import RACINE

CASE_OUVERTE = re.compile(r"^\s*[-*]\s*\[ \]\s*(.+)$")
REFERENCE = re.compile(r"(?:issues/|#)(\d+)\b")


def references(texte):
    """Numéros d'issues cités dans un texte (`#106` ou `.../issues/106`)."""
    return {int(n) for n in REFERENCE.findall(texte)}


def comparer(backlog, issues):
    """Renvoie (issues ouvertes absentes du backlog, cases non cochées sans issue).

    `issues` est une liste de dictionnaires {"number": int, "title": str}.
    """
    cites = references(backlog)
    absentes = [i for i in issues if i["number"] not in cites]
    cases = []
    for ligne in backlog.splitlines():
        m = CASE_OUVERTE.match(ligne)
        if m and not references(ligne):
            cases.append(m.group(1).strip())
    return absentes, cases


def rapport(absentes, cases):
    """Rapport en Markdown, lisible dans le résumé d'un workflow."""
    if not absentes and not cases:
        return "Backlog et issues ouvertes sont alignés."
    morceaux = []
    if absentes:
        morceaux.append("### Issues ouvertes que BACKLOG.md ne cite pas\n")
        morceaux += [f"- #{i['number']} {i['title']}" for i in absentes]
    if cases:
        morceaux.append("\n### Cases non cochées sans issue\n")
        morceaux += [f"- {c}" for c in cases]
    return "\n".join(morceaux)


def issues_ouvertes(depot, jeton):
    """Issues ouvertes du dépôt, hors pull requests (pagination par 100)."""
    issues, page = [], 1
    while True:
        url = f"https://api.github.com/repos/{depot}/issues?state=open&per_page=100&page={page}"
        requete = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {jeton}",
            "User-Agent": "agenda-nuit-tunis-synchro",
        })
        with urllib.request.urlopen(requete, timeout=30) as reponse:
            lot = json.load(reponse)
        # le ticket de tri des comptes (refait chaque lundi par tri_comptes.py) n'est pas un point du backlog
        issues += [{"number": i["number"], "title": i["title"]} for i in lot if "pull_request" not in i
                   and "tri-comptes" not in {e.get("name") for e in i.get("labels") or []}]
        if len(lot) < 100:
            return issues
        page += 1


def main():
    backlog = (RACINE / "BACKLOG.md").read_text(encoding="utf-8")
    depot = os.environ.get("GITHUB_REPOSITORY", "")
    jeton = os.environ.get("GITHUB_TOKEN", "")
    if not depot or not jeton:
        print("Pas de dépôt ou de jeton GitHub : relevé local seulement.")
        cases = comparer(backlog, [])[1]
        print(rapport([], cases))
        return 0
    absentes, cases = comparer(backlog, issues_ouvertes(depot, jeton))
    texte = rapport(absentes, cases)
    print(texte)
    resume = os.environ.get("GITHUB_STEP_SUMMARY")
    if resume:
        with open(resume, "a", encoding="utf-8") as f:
            f.write("## Synchro tickets\n\n" + texte + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
