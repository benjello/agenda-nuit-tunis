"""Fiche de chaque lieu de la page /clubs/ : photo, bio, lien et dernières affiches.

Deux sources, ce que le lieu publie lui-même :
- son compte Instagram (via Apify, clé APIFY_TOKEN) : photo de profil, bio, lien du site, 3 dernières affiches ;
- son site, s'il en a un : image de partage (og:image) et fiche schema.org (horaires, gamme de prix, téléphone).

Les images Instagram expirent : elles sont gardées dans assets/clubs/ (réduites), et chaque vignette renvoie
vers la publication d'origine. Écrit _data/fiches_clubs.json. Chaque lieu est relu au plus une fois par semaine.

Usage : python3 -m scrapers.fiches_clubs [--force]
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from urllib.parse import urljoin

from .commun import RACINE, meta, page, slug
from .sources.facebook import appeler_apify
from .sources.facebook_programmes import enregistrer_image

FICHIER = RACINE / "_data" / "fiches_clubs.json"
CLUBS = RACINE / "_data" / "clubs.json"
DOSSIER = RACINE / "assets" / "clubs"
JOURS_ENTRE_DEUX = 7
MAX_INSTAGRAM = 40   # comptes lus par passage (coût Apify)
AFFICHES = 3
VERSION_SITE = 2  # 2 : carte (menu) et cuisine lues sur le site ; une fiche plus ancienne est relue


def depuis_instagram(item: dict, nom: str) -> dict:
    """Profil Instagram (format de apify/instagram-scraper, resultsType « details »)."""
    dossier = DOSSIER / slug(nom)[:50]
    dossier.mkdir(parents=True, exist_ok=True)
    fiche = {"bio": (item.get("biography") or "").strip(), "abonnes": item.get("followersCount"),
             "site_insta": item.get("externalUrl") or ""}
    photo = item.get("profilePicUrlHD") or item.get("profilePicUrl")
    if photo:
        try:
            fiche["photo"] = enregistrer_image(photo, dossier, "profil")
        except Exception as exc:  # noqa: BLE001 — image illisible : la fiche reste sans photo
            print(f"  {nom} : photo de profil illisible ({exc})")
    affiches = []
    for p in sorted(item.get("latestPosts") or [], key=lambda p: p.get("timestamp") or "", reverse=True):
        if p.get("type") == "Video" and not p.get("displayUrl"):
            continue
        url_img, lien = p.get("displayUrl"), p.get("url") or (f"https://www.instagram.com/p/{p['shortCode']}/" if p.get("shortCode") else "")
        if not url_img or not lien:
            continue
        try:
            chemin = enregistrer_image(url_img, dossier, p.get("shortCode") or slug(lien)[-20:])
        except Exception:  # noqa: BLE001
            continue
        affiches.append({"image": chemin, "lien": lien, "date": (p.get("timestamp") or "")[:10]})
        if len(affiches) == AFFICHES:
            break
    fiche["affiches"] = affiches
    return {k: v for k, v in fiche.items() if v not in (None, "", [])}


def depuis_site(url: str) -> dict:
    """Image de partage et fiche schema.org (LocalBusiness, NightClub, BarOrPub…) du site du lieu."""
    soup = page(url)
    fiche = {}
    image = meta(soup, "og:image")
    if image.startswith("http"):
        fiche["image_site"] = image
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or "")
        except ValueError:
            continue
        for o in d if isinstance(d, list) else d.get("@graph", [d]) if isinstance(d, dict) else []:
            if not isinstance(o, dict):
                continue
            if o.get("openingHours") and "horaires_site" not in fiche:
                h = o["openingHours"]
                fiche["horaires_site"] = ", ".join(h) if isinstance(h, list) else str(h)
            if o.get("priceRange") and "prix_site" not in fiche:
                fiche["prix_site"] = str(o["priceRange"])
            if o.get("telephone") and "telephone_site" not in fiche:
                fiche["telephone_site"] = str(o["telephone"])
            m = o.get("hasMenu") or o.get("menu")
            m = m.get("url") or m.get("@id") if isinstance(m, dict) else m
            if isinstance(m, str) and m.startswith("http") and "menu_site" not in fiche:
                fiche["menu_site"] = m
            if o.get("servesCuisine") and "cuisine_site" not in fiche:
                c = o["servesCuisine"]
                fiche["cuisine_site"] = ", ".join(c) if isinstance(c, list) else str(c)
    if "menu_site" not in fiche:  # sinon un lien « Menu » / « La carte » de la page d'accueil
        for a in soup.find_all("a", href=True):
            texte = " ".join(a.get_text(" ").split()).lower()
            if re.fullmatch(r"(notre |la |le )?(menus?|carte|nos menus|menu & carte|food menu)|قائمة الطعام|المنيو", texte) \
                    or re.search(r"(?i)/(menus?|carte|la-carte)(/|\.pdf|$)", a["href"]):
                fiche["menu_site"] = urljoin(url, a["href"])
                break
    return fiche


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    force = "--force" in argv
    try:
        lieux = json.loads(CLUBS.read_text()).get("lieux") or []
    except (FileNotFoundError, json.JSONDecodeError):
        lieux = []
    try:
        fiches = json.loads(FICHIER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        fiches = {}
    aujourd_hui = dt.date.today()

    def a_relire(nom: str) -> bool:
        lu = (fiches.get(nom) or {}).get("lu_le")
        return force or not lu or (aujourd_hui - dt.date.fromisoformat(lu)).days >= JOURS_ENTRE_DEUX

    # 1. Instagram, en un seul appel Apify pour tous les comptes à relire
    cle = (os.environ.get("APIFY_TOKEN") or "").strip()
    # les restaurants passent après les clubs et bars (MAX_INSTAGRAM comptes par passage)
    ordre = sorted(lieux, key=lambda x: x.get("type") == "restaurant")
    comptes = {x["instagram"]: x["nom"] for x in ordre if x.get("instagram") and a_relire(x["nom"])}
    comptes = dict(list(comptes.items())[:MAX_INSTAGRAM])
    if comptes and cle:
        try:
            items = appeler_apify("apify/instagram-scraper", {
                "directUrls": [f"https://www.instagram.com/{c}/" for c in comptes],
                "resultsType": "details", "resultsLimit": 1}, cle)
        except Exception as exc:  # noqa: BLE001 — Apify en panne : on garde les fiches d'avant
            print(f"fiches clubs : Apify illisible ({exc})")
            items = []
        for item in items:
            nom = comptes.get((item.get("username") or "").lower()) or comptes.get(item.get("username") or "")
            if not nom:
                continue
            fiches[nom] = {**(fiches.get(nom) or {}), **depuis_instagram(item, nom), "lu_le": aujourd_hui.isoformat()}
    elif comptes:
        print("fiches clubs : APIFY_TOKEN manquant, Instagram non lu.")

    # 2. Sites des lieux (gratuit)
    for x in lieux:
        site = x.get("site")
        deja = (fiches.get(x["nom"]) or {}).get("site_lu") == VERSION_SITE
        if not site or (deja and not a_relire(x["nom"])) or "instagram.com" in site or "facebook.com" in site:
            continue
        try:
            infos = depuis_site(site)
        except Exception as exc:  # noqa: BLE001 — site en panne : on passe au suivant
            print(f"  {x['nom']} : site illisible ({exc})")
            continue
        fiches[x["nom"]] = {**(fiches.get(x["nom"]) or {}), **infos, "site_lu": VERSION_SITE, "lu_le": aujourd_hui.isoformat()}

    FICHIER.write_text(json.dumps(fiches, ensure_ascii=False, indent=1, sort_keys=True))
    print(f"fiches clubs : {len(fiches)} fiche(s), dont {sum('photo' in f for f in fiches.values())} avec photo Instagram "
          f"et {sum('image_site' in f for f in fiches.values())} avec image du site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
