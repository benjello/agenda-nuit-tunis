"""Scraper générique : toute page qui décrit ses événements en schema.org (JSON-LD).

Beaucoup de sites (WordPress avec une extension d'agenda, billetteries…) le font
sans le savoir. Pour une telle source, il suffit d'ajouter une ligne au registre
avec « scraper: jsonld », sans écrire de code.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import html
import re

from ..commun import Evenement, json_ld_evenements, page, propre, resume


TUNIS = ZoneInfo("Africa/Tunis")


def _date(v):
    if not isinstance(v, str) or not v:
        return None
    try:
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
        # Heure avec fuseau (souvent UTC) : on la ramène à l'heure de Tunis.
        return d.astimezone(TUNIS).replace(tzinfo=None) if d.tzinfo else d
    except ValueError:
        return None


def _lieu(loc):
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    if isinstance(loc, str):
        return loc, ""
    adr = loc.get("address", "") if isinstance(loc, dict) else ""
    if isinstance(adr, dict):
        adr = ", ".join(x for x in (adr.get("streetAddress"), adr.get("addressLocality")) if x)
    return propre(loc.get("name", "") if isinstance(loc, dict) else ""), propre(adr)


def _texte(v) -> str:
    """Description schema.org : souvent du HTML échappé."""
    if not isinstance(v, str):
        return ""
    return re.sub(r"<[^>]+>", " ", html.unescape(v)).strip()


def prix_offre(offre: dict) -> str:
    """Prix d'une offre schema.org ; « Gratuit » si le prix est 0, « Complet » si épuisé."""
    p = offre.get("price")
    if p in (0, "0", "0.00", "0.0", 0.0):
        prix = "Gratuit"
    else:
        prix = f"{p} {offre.get('priceCurrency', '')}".strip() if p else ""
    if re.search(r"SoldOut", str(offre.get("availability") or ""), re.I):
        prix = f"{prix} · Complet" if prix and prix != "Gratuit" else "Complet"
    return prix


def depuis_json_ld(objets: list[dict], url_page: str) -> list[Evenement]:
    res = []
    for o in objets:
        debut = _date(o.get("startDate"))
        if not debut or not o.get("name"):
            continue
        lieu, adresse = _lieu(o.get("location") or {})
        offre = o.get("offers") or {}
        if isinstance(offre, list):
            offre = offre[0] if offre else {}
        prix = prix_offre(offre)
        image = o.get("image")
        image = image[0] if isinstance(image, list) and image else image
        image = image.get("url") if isinstance(image, dict) else image
        res.append(Evenement(titre=propre(o["name"]), debut=debut, fin=_date(o.get("endDate")),
                             lien=o.get("url") or url_page, lieu=lieu, adresse=adresse, prix=prix,
                             image=image if isinstance(image, str) else "",
                             description=resume(_texte(o.get("description")))))
    return res


def recuperer(source: dict) -> list[Evenement]:
    return depuis_json_ld(json_ld_evenements(page(source["url"])), source["url"])
