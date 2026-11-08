"""Résumé d'une pull request pour la relecture (appelé par le workflow « Contribution »).

Classe les fichiers modifiés en « données » (sans risque) et « sensibles » (code exécuté par
GitHub Actions, avec les secrets). Écrit le résumé dans la page de l'exécution et un
avertissement par fichier sensible. N'échoue jamais : c'est une aide à la relecture.
"""
import fnmatch
import os
import subprocess

# Fichiers que les contributeurs touchent normalement : données, pages d'exemple, notes.
DONNEES = [
    "_data/sources.yml", "_data/sources_recherchees.yml", "_data/descriptifs_manuels.yml",
    "_data/lieux_coords.yml", "_data/lieux_alias.yml", "_data/artistes.yml", "_data/festivals.yml",
    "_data/musees.yml", "_data/films_infos.yml", "_data/i18n.yml", "_data/villes.yml",
    "_events/*", "tests/fixtures/*", "bilan-sources/*", "*.md",
]
# Fichiers qui s'exécutent dans GitHub Actions ou sur le site : à lire ligne par ligne.
# Un motif qui commence par « / » ne vaut qu'à la racine du dépôt.
SENSIBLES = [
    ".github/*", "scrapers/*", "requirements*.txt", "Gemfile*", "_config.yml",
    "_layouts/*", "_includes/*", "assets/*.js", "sw.js", "/*.html",
]
CONFIANCE = {"OWNER", "MEMBER", "COLLABORATOR"}


def correspond(fichier, motifs):
    for m in motifs:
        if m.startswith("/"):
            if "/" not in fichier and fnmatch.fnmatch(fichier, m[1:]):
                return True
        elif fnmatch.fnmatch(fichier, m):
            return True
    return False


def classer(fichiers):
    donnees, sensibles, autres = [], [], []
    for f in fichiers:
        if correspond(f, SENSIBLES):
            sensibles.append(f)
        elif correspond(f, DONNEES):
            donnees.append(f)
        else:
            autres.append(f)
    return donnees, sensibles, autres


def main():
    base = os.environ.get("BASE", "main")
    fichiers = subprocess.run(["git", "diff", "--name-only", f"origin/{base}...HEAD"],
                              capture_output=True, text=True, check=True).stdout.split()
    donnees, sensibles, autres = classer(fichiers)
    association = os.environ.get("ASSOCIATION", "")
    exterieur = association not in CONFIANCE
    lignes = ["## Contribution", ""]
    lignes.append(f"Auteur : `{os.environ.get('AUTEUR', '?')}` "
                  + ("(contribution extérieure)" if exterieur else f"({association.lower()})"))
    lignes.append("")
    for titre, liste in (("Données", donnees), ("⚠️ Code ou workflows : relire ligne par ligne", sensibles),
                         ("Autres fichiers", autres)):
        if liste:
            lignes.append(f"**{titre}** ({len(liste)})")
            lignes += [f"- `{f}`" for f in liste]
            lignes.append("")
    if exterieur and sensibles:
        lignes.append("Cette PR extérieure touche du code : ne pas fusionner sans avoir tout lu "
                      "(un workflow modifié pourrait lire les secrets une fois fusionné).")
    texte = "\n".join(lignes)
    print(texte)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as sortie:
            sortie.write(texte + "\n")
    if exterieur:
        for f in sensibles:
            print(f"::warning file={f}::Fichier sensible modifié par une contribution extérieure")


if __name__ == "__main__":
    main()
