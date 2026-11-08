"""Complète les champs calculés de tous les événements, y compris ceux saisis à la main :
ville, « en famille », et date d'ajout (pour « Nouveau cette semaine »).

  python3 -m scrapers.ranger
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess

import yaml

from .commun import RACINE, age_conseille, est_famille, langues_annoncees
from .villes import ville


def _date_ajout(f) -> str:
    """Premier commit qui a ajouté le fichier, sinon aujourd'hui."""
    try:
        r = subprocess.run(["git", "log", "--diff-filter=A", "--format=%as", "--", str(f)],
                           cwd=RACINE, capture_output=True, text=True, timeout=20)
        dates = r.stdout.split()
        return dates[-1] if dates else dt.date.today().isoformat()
    except (OSError, subprocess.SubprocessError):
        return dt.date.today().isoformat()


def _poser(tete: str, cle: str, valeur: str | None) -> str:
    """Ajoute, remplace ou retire « cle: valeur » dans le front matter."""
    ligne = f"{cle}: {valeur}" if valeur is not None else ""
    if re.search(rf"^{cle}: ", tete, re.M):
        return re.sub(rf"^{cle}: .*(\n|$)", (ligne + r"\1") if ligne else "", tete, flags=re.M).rstrip("\n")
    return tete + ("\n" + ligne if ligne else "")


def jeune_public() -> set[str]:
    """Sources dont tout ce qu'elles annoncent est pour les enfants (« jeune_public: true »)."""
    sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []
    return {s["id"] for s in sources if s.get("jeune_public")}


def ranger(f, enfants: set[str] = frozenset()) -> bool:
    t = f.read_text()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)", t, re.S)
    if not m:
        return False
    tete, corps = m.group(1), m.group(2)
    champ = lambda k: (re.search(rf'^{k}: "?(.*?)"?$', tete, re.M) or [None, ""])[1]  # noqa: E731
    nouvelle = _poser(tete, "ville", f'"{ville(champ("venue"), champ("address"))}"')
    famille = champ("source") in enfants or est_famille(champ("title"), corps)
    nouvelle = _poser(nouvelle, "famille", "true" if famille else None)
    age = age_conseille(champ("title"), corps) if famille else None
    nouvelle = _poser(nouvelle, "age", f'"{age}"' if age else None)
    langues = langues_annoncees(champ("title"), corps)
    nouvelle = _poser(nouvelle, "langues", "[" + ", ".join(f'"{x}"' for x in langues) + "]" if langues else None)
    if not re.search(r"^ajoute: ", nouvelle, re.M):
        nouvelle = _poser(nouvelle, "ajoute", f'"{_date_ajout(f)}"')
    if nouvelle == tete:
        return False
    f.write_text(t.replace(tete, nouvelle, 1))
    return True


def main() -> int:
    enfants = jeune_public()
    n = sum(ranger(f, enfants) for f in sorted((RACINE / "_events").rglob("*.md")) if f.name != "README.md")
    print(f"{n} événement(s) rangé(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
