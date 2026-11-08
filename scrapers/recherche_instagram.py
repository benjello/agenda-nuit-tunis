"""Cherche des comptes Instagram par mots-clés (via Apify), pour trouver de nouvelles sources.

Usage : python3 -m scrapers.recherche_instagram "gammarth club" "la marsa bar"
Affiche pour chaque compte trouvé : nom, abonnés, date de la dernière publication, bio.
Rien n'est écrit dans le site : on choisit ensuite à la main quoi ajouter au registre.
"""
from __future__ import annotations

import os
import sys

from .sources.facebook import appeler_apify


def main(mots: list[str]) -> int:
    cle = (os.environ.get("APIFY_TOKEN") or "").strip()  # un secret collé finit souvent par un retour à la ligne
    if not cle:
        print("APIFY_TOKEN manquant")
        return 1
    vus = set()
    for m in mots:
        try:
            items = appeler_apify("apify/instagram-scraper", {
                "search": m, "searchType": "user", "searchLimit": 20,
                "resultsType": "details", "resultsLimit": 1}, cle)
        except Exception as exc:  # noqa: BLE001 — Apify en panne pour un mot : on passe au suivant
            print(f"\n## {m} : erreur {exc}")
            continue
        print(f"\n## {m} : {len(items)} compte(s)")
        def derniere_pub(i):
            return max((p.get("timestamp") or "" for p in i.get("latestPosts") or []), default="")
        for i in sorted(items, key=derniere_pub, reverse=True):
            nom = i.get("username")
            if not nom or nom in vus:
                continue
            vus.add(nom)
            derniere = max((p.get("timestamp") or "" for p in i.get("latestPosts") or []), default="")
            bio = (i.get("biography") or "").replace("\n", " ")[:100]
            print(f"- @{nom} | {i.get('fullName', '')} | {i.get('followersCount', '?')} abonnés | "
                  f"dernière publication {derniere[:10] or '?'} | {bio}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
