"""Comptes Instagram à brancher, repérés par les hashtags de la nuit (via Apify).

On lit les dernières publications de hashtags comme #gammarth ou #hammametnightlife, on garde celles
qui annoncent une soirée (DJ, party, club, karaoké…), et on compte, par compte, combien il en publie.
Les comptes déjà suivis (_data/sources.yml, _data/clubs.yml) sont mis à part.

Résultat : _data/comptes_proposes.json (classé du plus actif au moins actif) et un tableau dans le
résumé de l'exécution GitHub. Rien n'est branché tout seul : on choisit ensuite quoi ajouter au registre.

Usage : python3 -m scrapers.recherche_hashtags [hashtag …]
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import os
import re
import sys

import yaml

from .commun import RACINE, categorie_du_titre
from .sources.facebook import appeler_apify

FICHIER = RACINE / "_data" / "comptes_proposes.json"
HASHTAGS = ["gammarth", "lamarsa", "hammametnightlife", "hammamet", "tunisnightlife", "tunisnight", "tunisparty",
            "soireetunis", "sousse", "djerbanight", "monastir", "tunisiannightlife", "clubbingtunisie",
            "tunisiadj", "partytunisia", "nightlifetunisia", "tunistechno", "afrohousetunisia", "yasminehammamet"]
PAR_HASHTAG = 40     # publications lues par hashtag (coût Apify : environ 0,2 centime l'une)
SOIREE = re.compile(r"(?i)\bparty\b|\bsoir[ée]e\b|\bnight\b|\btonight\b|\bce soir\b|\bdj\b|\bclub|\bline ?up\b|\bguest\b"
                    r"|\bresa\b|\br[ée]servation|\btable\b|\bentr[ée]e\b|سهرة|حفل")
# Retransmissions de matchs (bars à sport) : pas une soirée, même si la publication dit « ce soir » ou « réservez ».
MATCH = re.compile(r"(?i)\bmatch\b|\bligue\b|champions league|premier league|\bliga\b|\bderby\b|\bfoot(ball)?\b"
                   r"|coup d'envoi|kick ?off|\bbein\b|\bcan 20\d\d|coupe du monde|world cup|retransmission|مباراة|ماتش")
# Lieu cité par un artiste ou un organisateur : « 📍 B7L9, La Marsa », « at @jetset_tn », « chez @moods.gammarth »
EPINGLE = re.compile(r"📍\s*([^\n#]{3,60})")
CITE = re.compile(r"(?i)(?:\bat|\bà|\bau|\bchez|📍)\s*@([\w.]+)")
# Préfiltre : comptes qui utilisent les hashtags sans organiser de soirées (immobilier, voyages, hôtels, boutiques…)
HORS_NUIT = re.compile(r"(?i)immo|remax|voyage|travel|tours?(?![a-z])|trip|wakacj|suitcase|h[ôo]tel|thalasso|residence|palace"
                       r"|beds\b|perfume|parfum|\bmode\b|store|coupon|salon de th|coffee|caf[ée]|magazine|news|booklover"
                       r"|totebag|smartlab|smart-lab|univers\.a\.i|sport")
JOURS_MAX = 120      # un compte qui n'a rien publié depuis 4 mois n'est pas proposé
EXCLUS = RACINE / "_data" / "comptes_exclus.yml"  # faux positifs cochés dans le ticket de tri (scrapers/tri_comptes.py)


def exclus() -> set[str]:
    return {str(c).lower().lstrip("@") for c in (yaml.safe_load(EXCLUS.read_text()) or [])} if EXCLUS.exists() else set()


def prefiltre(c: dict, ecartes: set[str], aujourd_hui: dt.date | None = None) -> str:
    """Raison d'écarter un compte avant le tri à la main ("" s'il reste proposé)."""
    aujourd_hui = aujourd_hui or dt.date.today()
    if c["compte"] in ecartes:
        return "faux positif"
    if HORS_NUIT.search(f"{c['compte']} {c['nom']}"):
        return "hors nuit"
    if c.get("cite") and not c["soirees"]:
        return ""  # seulement cité par d'autres : à vérifier
    if not c["derniere"] or (aujourd_hui - dt.date.fromisoformat(c["derniere"])).days > JOURS_MAX:
        return "inactif"
    return ""


def deja_suivis() -> set[str]:
    comptes = set()
    for s in yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []:
        c = (s.get("options") or {}).get("compte")
        if c:
            comptes.add(c.lower())
    clubs = RACINE / "_data" / "clubs.yml"
    for c in (yaml.safe_load(clubs.read_text()) or []) if clubs.exists() else []:
        if c.get("instagram"):
            comptes.add(c["instagram"].lower())
    return comptes


def lieux_cites(texte: str) -> list[str]:
    """Lieux nommés dans une légende : comptes après « at / à / chez / 📍 », puis texte après 📍."""
    lieux = [f"@{h.lower().rstrip('.')}" for h in CITE.findall(texte)]
    lieux += [" ".join(m.split()).strip(" ,.-|") for m in EPINGLE.findall(texte) if not m.strip().startswith("@")]
    return [x for x in dict.fromkeys(lieux) if x]


def classer(publications: list[dict], suivis: set[str]) -> list[dict]:
    """Par compte : nombre de publications de soirée, hashtags où il apparaît, dernière date, exemple,
    et lieux cités (un artiste ou un organisateur annonce le lieu dans sa légende). Un lieu cité par un autre
    compte (« at @club ») est proposé lui aussi, avec le nombre de fois où il est cité."""
    par_compte: dict[str, dict] = {}

    def fiche(compte: str, nom: str = "") -> dict:
        return par_compte.setdefault(compte, {"compte": compte, "nom": nom, "soirees": 0, "cite": 0,
                                              "hashtags": collections.Counter(), "lieux": collections.Counter(),
                                              "derniere": "", "exemple": ""})

    for p in publications:
        compte = (p.get("ownerUsername") or "").lower()
        texte = p.get("caption") or ""
        if not compte or not (SOIREE.search(texte) or categorie_du_titre(texte)) or MATCH.search(texte):
            continue
        c = fiche(compte, p.get("ownerFullName") or "")
        c["nom"] = c["nom"] or p.get("ownerFullName") or ""
        c["soirees"] += 1
        for lieu in lieux_cites(texte):
            if lieu != f"@{compte}":
                c["lieux"][lieu] += 1
                if lieu.startswith("@"):
                    fiche(lieu[1:])["cite"] += 1
        if p.get("_hashtag"):
            c["hashtags"][p["_hashtag"]] += 1
        date = (p.get("timestamp") or "")[:10]
        if date >= c["derniere"]:
            c["derniere"], c["exemple"] = date, p.get("url") or ""
    sortie = []
    for c in par_compte.values():
        c["hashtags"] = [h for h, _ in c["hashtags"].most_common(4)]
        c["lieux"] = [x for x, _ in c["lieux"].most_common(3)]
        c["suivi"] = c["compte"] in suivis
        sortie.append(c)
    # les nouveaux d'abord, puis du plus actif au moins actif, puis du plus récent
    return sorted(sortie, key=lambda c: (c["suivi"], -(c["soirees"] + c["cite"]), "".join(chr(255 - ord(x)) for x in c["derniere"])))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cle = (os.environ.get("APIFY_TOKEN") or "").strip()
    if not cle:
        print("APIFY_TOKEN manquant")
        return 1
    hashtags = [h.strip().lstrip("#").replace(" ", "") for h in (argv or HASHTAGS) if h.strip()]
    publications = []
    for h in hashtags:
        try:
            items = appeler_apify("apify/instagram-scraper", {
                "directUrls": [f"https://www.instagram.com/explore/tags/{h}/"],
                "resultsType": "posts", "resultsLimit": PAR_HASHTAG}, cle)
        except Exception as exc:  # noqa: BLE001 — un hashtag en panne : on passe au suivant
            print(f"#{h} : erreur {exc}")
            continue
        print(f"#{h} : {len(items)} publication(s)")
        for i in items:
            i["_hashtag"] = h
        publications += items
    comptes, ecartes = [], exclus()
    for c in classer(publications, deja_suivis()):
        raison = "" if c["suivi"] else prefiltre(c, ecartes)
        if raison:
            print(f"  écarté ({raison}) : @{c['compte']} {c['nom']}")
        else:
            comptes.append(c)
    FICHIER.write_text(json.dumps({"lu_le": dt.date.today().isoformat(), "hashtags": hashtags, "comptes": comptes},
                                  ensure_ascii=False, indent=1))
    lignes = ["| Compte | Nom | Affiches de soirée | Cité | Lieux cités | Hashtags | Dernière | Déjà suivi |",
              "|---|---|---|---|---|---|---|---|"]
    for c in comptes[:60]:
        lignes.append(f"| [@{c['compte']}](https://www.instagram.com/{c['compte']}/) | {c['nom']} | {c['soirees']} | {c['cite'] or ''} | "
                      f"{', '.join(c['lieux'])} | {', '.join('#' + h for h in c['hashtags'])} | {c['derniere']} | {'oui' if c['suivi'] else ''} |")
    texte = "## Comptes repérés par les hashtags\n\n" + "\n".join(lignes) + "\n"
    print(texte)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(texte)
    return 0


if __name__ == "__main__":
    sys.exit(main())
