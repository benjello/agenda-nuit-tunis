"""Événements d'une page Facebook, via Apify.

Facebook bloque les robots et son API ne donne plus les événements des pages
qu'à leurs administrateurs. Apify (apify.com) lit les événements publics, sans
compte Facebook, depuis ses propres adresses, et nous renvoie du JSON.

- Clé : variable d'environnement APIFY_TOKEN (secret du dépôt GitHub). Sans clé,
  la source est « en attente » et rien n'est effacé.
- Coût : facturé à l'événement lu (environ 1 centime). Le compte gratuit
  d'Apify offre 5 $ par mois ; régler « tous_les_jours » dans le registre pour
  ne pas relire chaque page tous les jours.
- Seuls les événements Facebook sont lus, pas les publications (affiches).

Options :
  page        nom de la page (facebook.com/<page>) ou URL complète d'un groupe
  recherche   à la place de page : liste de mots-clés (« soirée Tunis », « party Gammarth »)
              cherchés dans les événements publics de Facebook ; trouve aussi des organisateurs
              à brancher comme sources (leur nom est dans le lieu ou le lien de l'événement)
  max         nombre maximum d'événements lus par passage (défaut 30)
  acteur      acteur Apify (défaut apify/facebook-events-scraper)
"""
from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

import requests

from ..commun import EnAttente, Evenement, propre

ACTEUR = "apify/facebook-events-scraper"
TUNIS = ZoneInfo("Africa/Tunis")


def url_evenements(page: str) -> str:
    if page.startswith("http"):
        url = page.rstrip("/")
        return url if url.endswith("events") else url + ("/events" if "/groups/" in url else "/upcoming_hosted_events")
    return f"https://www.facebook.com/{page.strip('/')}/upcoming_hosted_events"


def appeler_apify(acteur: str, entree: dict, cle: str) -> list[dict]:
    r = requests.post(
        f"https://api.apify.com/v2/acts/{acteur.replace('/', '~')}/run-sync-get-dataset-items",
        params={"token": cle}, json=entree, timeout=320)
    r.raise_for_status()
    return r.json()


def _date(v) -> dt.datetime | None:
    if isinstance(v, (int, float)):  # horodatage Unix
        return dt.datetime.fromtimestamp(v, TUNIS).replace(tzinfo=None)
    if not isinstance(v, str) or not v:
        return None
    try:
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(TUNIS).replace(tzinfo=None) if d.tzinfo else d


def convertir(item: dict, source: dict) -> Evenement | None:
    """Accepte les champs des principaux acteurs Apify (ils varient un peu)."""
    if item.get("isCanceled") or item.get("isPast") or item.get("error"):
        return None
    titre = propre(item.get("name") or item.get("title"))
    debut = next((d for d in map(_date, (item.get(k) for k in
                  ("utcStartDate", "startISO", "startDate", "startTimestamp", "startTime"))) if d), None)
    lien = item.get("url") or item.get("eventUrl")
    if not (titre and debut and lien):
        return None
    fin = next((d for d in map(_date, (item.get(k) for k in
                ("utcEndDate", "endISO", "endDate", "endTimestamp"))) if d), None)
    loc = item.get("location") if isinstance(item.get("location"), dict) else {}
    lieu = propre(loc.get("name") or item.get("locationName")) or source.get("options", {}).get("lieu") or source["nom"]
    adresse = propre(loc.get("streetAddress") or item.get("locationAddress") or item.get("address") or "")
    if isinstance(item.get("address"), dict):
        adresse = propre(item["address"].get("streetAddress", ""))
    return Evenement(titre=titre, debut=debut, fin=fin, lien=lien.split("?")[0],
                     lieu=lieu, adresse=adresse, categorie=source.get("categorie", ""))


def recuperer(source: dict) -> list[Evenement]:
    cle = (os.environ.get("APIFY_TOKEN") or "").strip()  # un secret collé finit souvent par un retour à la ligne
    if not cle:
        raise EnAttente("clé APIFY_TOKEN pas encore configurée")
    o = source.get("options", {})
    if o.get("recherche"):
        entree = {"searchQueries": list(o["recherche"]), "maxEvents": o.get("max", 30)}
    else:
        entree = {"startUrls": [url_evenements(o.get("page") or source["url"])],
                  "maxEvents": o.get("max", 30)}
    items = appeler_apify(o.get("acteur", ACTEUR), entree, cle)
    if not isinstance(items, list):
        raise RuntimeError(f"réponse Apify inattendue : {str(items)[:200]}")
    evenements = [e for e in (convertir(i, source) for i in items) if e]
    print(f"  {source['id']} : {len(items)} élément(s) renvoyé(s) par Apify, {len(evenements)} événement(s) gardé(s)")
    for i in items:
        if not convertir(i, source) and not i.get("error"):
            print(f"    écarté : {i.get('name')!r} début={i.get('utcStartDate') or i.get('startISO') or i.get('startTime')} "
                  f"passé={i.get('isPast')} annulé={i.get('isCanceled')}")
    erreurs = [i for i in items if i.get("error") and i.get("error") != "no_items"]  # no_items : rien de récent, pas une panne
    if erreurs and not evenements:
        raise RuntimeError(f"Apify : {str(erreurs[0])[:250]}")
    return evenements
