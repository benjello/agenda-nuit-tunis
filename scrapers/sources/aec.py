"""Agenda culturel des sites qui vendent leurs billets avec AEC (Institut français de Tunisie).

La page https://www.institutfrancais-tunisie.com/list-agenda est remplie en JavaScript à partir
d'une API publique (tunisie.aec.app). On l'interroge directement, sans navigateur :
  1. app_status donne un jeton de session anonyme (extranetSession) ;
  2. availableEventsToday donne les événements à venir, chacun avec sa fiche
     (details-agenda/?eventId=…), son affiche, son prix, sa salle et sa notice.
La clé d'API est celle que le site envoie à chaque visiteur : on la relit dans la page,
sinon on prend celle des options.

Options :
  page      page d'agenda du site (défaut : l'URL de la source)
  api       adresse de l'API (défaut : https://tunisie.aec.app/api/public/core/v1/events/)
  extranet  domaine de l'extranet (défaut : tunisie.extranet-aec.com)
  api_key   clé publique, si la page ne la donne pas
  lieu      lieu par défaut
"""
from __future__ import annotations

import ast
import datetime as dt
import html
import re

from bs4 import BeautifulSoup

from ..commun import Evenement, _session, propre, resume, titre_film

API = "https://tunisie.aec.app/api/public/core/v1/events/"
EXTRANET = "tunisie.extranet-aec.com"
IMAGE = "https://res.cloudinary.com/aec/image/upload/c_fit,f_auto,h_360,q_auto,w_640/v1/"
_CLE = re.compile(r"""api_?key["']?\s*[:=]\s*["']([A-Za-z0-9+/=]{40,})""", re.I)
# « Billetterie évènements|Cinéma » → catégorie du site
_GENRES = {"cinéma": "cinema", "cinema": "cinema", "exposition": "expo", "musique": "musique", "livre": "litterature",
           "théâtre": "theatre", "theatre": "theatre", "danse": "danse", "société civile": "conference",
           "débat": "conference", "conférence": "conference", "art visuel": "autre"}
_PAS_UN_FILM = re.compile(r"courts?[- ]m[ée]trages|\bcycle\b|\bprogramme\b|\bnuit\b|\bfestival\b|\batelier", re.I)


def _date(v) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(v)[:19]) if v else None
    except ValueError:
        return None


def _lieu(o: dict, defaut: str) -> tuple[str, str]:
    """« Tunis - IFT » → « Institut français de Tunis » ; « Sousse » → « Institut français de Sousse »."""
    nom = propre(o.get("event_location_name"))
    adresse = propre(o.get("event_location_address"))
    salle = propre(o.get("event_location_indication") or "")
    if nom == "all_etablishment_branchs" or not nom:
        ville = propre(o.get("event_location"))
        lieu = f"{defaut}, {ville}" if ville and ville.lower() not in defaut.lower() else defaut
    elif o.get("event_external_location"):
        lieu = propre(o.get("event_location")) or nom
    else:
        ville = re.split(r"\s*-\s*", nom)[0]
        lieu = f"Institut français de {ville}"
    if salle:
        lieu = f"{salle}, {lieu}"
    return lieu, adresse


def _image(o: dict) -> str:
    try:  # « [{'IDIMAGE': 272563, 'url': 'https://res.cloudinary.com/…'}] » (texte au format Python)
        images = ast.literal_eval(o.get("event_images") or "[]")
        if images and images[0].get("url"):
            return images[0]["url"]
    except (ValueError, SyntaxError, AttributeError, TypeError):
        pass
    rid = o.get("image_resource_id")
    return IMAGE + rid if rid else ""


def _prix(o: dict) -> str:
    try:
        p = float(o.get("product_price") or 0)
    except ValueError:
        return ""
    return "Gratuit" if p == 0 else f"{p:g} DT"


def _notice(o: dict) -> str:
    brut = o.get("product_description") or o.get("product_short_description") or ""
    soup = BeautifulSoup(html.unescape(brut).replace("<br>", "\n").replace("</p>", "\n"), "html.parser")
    return resume(soup.get_text(), 500)


def evenement(o: dict, defaut: str) -> Evenement | None:
    debut = _date(o.get("event_date"))
    titre = propre(html.unescape(o.get("product_name") or ""))
    lien = o.get("event_url") or ""
    if not (debut and titre and lien):
        return None
    fin = _date(o.get("raw_unformatted_event_end_date"))
    genre = str(o.get("categoryForAnalytics") or "").split("|")[-1].strip().lower()
    categorie = _GENRES.get(genre, "autre")
    lieu, adresse = _lieu(o, defaut)
    est_film = categorie == "cinema" and not fin and not _PAS_UN_FILM.search(titre)
    return Evenement(titre=titre_film(titre) if est_film else titre, debut=debut,
                     fin=fin if fin and fin.date() != debut.date() else None, lien=lien, lieu=lieu, adresse=adresse,
                     categorie=categorie, prix=_prix(o), image=_image(o), film=est_film,
                     seances=[debut] if est_film else [], description=_notice(o))


def depuis_api(objets: list[dict], defaut: str) -> list[Evenement]:
    return [e for e in (evenement(o, defaut) for o in objets if isinstance(o, dict)) if e]


def lire_api(options: dict, page_url: str) -> list[dict]:
    """Objets bruts de l'API : jeton de session anonyme, puis événements à venir."""
    cle = options.get("api_key", "")
    try:
        trouve = _CLE.search(_session.get(page_url, timeout=30).text)
        cle = trouve.group(1) if trouve else cle
    except Exception:  # noqa: BLE001 — la clé des options suffit
        pass
    if not cle:
        raise RuntimeError("clé d'API AEC introuvable (option api_key)")
    extranet = options.get("extranet", EXTRANET)
    entetes = {"api_key": cle, "extranet_url": extranet, "current_lang": "fr_FR",
               "Origin": "https://" + re.sub(r"^https?://([^/]+).*", r"\1", page_url),
               "Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}
    statut = _session.get(f"https://{extranet}/api/students/app_status?CURRENT_LANG=fr_FR", headers=entetes, timeout=30)
    statut.raise_for_status()
    entetes["extranet_session"] = statut.json().get("extranetSession", "")
    r = _session.get(options.get("api", API) + "availableEventsToday?eventType=&etablishmentBranchId=&CURRENT_LANG=fr_FR",
                     headers=entetes, timeout=30)
    r.raise_for_status()
    objets = r.json()
    if not isinstance(objets, list):
        raise RuntimeError("réponse inattendue de l'API AEC")
    return objets


def recuperer(source: dict) -> list[Evenement]:
    o = source.get("options") or {}
    page_url = o.get("page") or source["url"]
    return depuis_api(lire_api(o, page_url), o.get("lieu", source["nom"]))
