"""Scraper générique : flux RSS ou Atom d'événements.

La date de l'événement est cherchée dans le titre puis dans la description
(« 26.09.2026 », « 26 septembre 2026 à 19h00 »). Les éléments sans date sont ignorés :
dans un flux d'actualités, seuls ceux qui annoncent une date passent.

Options :
  lieu          : nom du lieu par défaut
  nettoyer_titre: expression régulière à retirer du titre (facultatif)
  garder        : expression régulière : seuls les éléments dont le titre ou le texte la contiennent
                  sont gardés (pour écarter bourses, appels à candidatures…)
  lire_page     : true pour ouvrir la page de chaque événement et y lire « Lieu : … » et
                  « Dates : 3–5 décembre 2026 » (l'IRMC organise souvent ailleurs que chez lui)
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from ..commun import Evenement, details_page, propre, resume, telecharger, toutes_dates

ATOM = "{http://www.w3.org/2005/Atom}"
_HEURE = re.compile(r"\b([01]?\d|2[0-3])\s*[hH:]\s*([0-5]\d)\b")


def _texte_html(h: str) -> str:
    return propre(BeautifulSoup(h or "", "html.parser").get_text(" "))


def _racine(xml: str):
    try:
        return ET.fromstring(xml.encode())
    except ET.ParseError:
        # Flux suivi de texte parasite (liens injectés après </rss>, cas de l'IRMC) : on coupe.
        fin = max(xml.rfind("</rss>") + 6, xml.rfind("</feed>") + 7)
        if fin <= 6:
            raise
        return ET.fromstring(xml[:fin].encode())


def elements(xml: str) -> list[dict]:
    racine = _racine(xml if isinstance(xml, str) else xml.decode("utf-8", "replace"))
    res = []
    for it in racine.iter("item"):
        res.append({"titre": it.findtext("title", ""), "lien": it.findtext("link", ""),
                    "description": it.findtext("description", ""), "categorie": it.findtext("category", "")})
    for it in racine.iter(f"{ATOM}entry"):
        lien = it.find(f"{ATOM}link")
        res.append({"titre": it.findtext(f"{ATOM}title", ""), "lien": lien.get("href", "") if lien is not None else "",
                    "description": it.findtext(f"{ATOM}summary", "") or it.findtext(f"{ATOM}content", ""),
                    "categorie": ""})
    return res


def depuis_flux(xml: str, source: dict) -> list[Evenement]:
    opts = source.get("options") or {}
    lieu = opts.get("lieu", source["nom"])
    res = []
    for el in elements(xml):
        titre = propre(el["titre"])
        description = _texte_html(el["description"])
        dates = toutes_dates(titre)
        if dates and not any(d.hour or d.minute for d in dates):
            # heure souvent dans la description : « … le 26 septembre 2026 à 19h00 »
            precises = [d for d in toutes_dates(description) if d.date() == dates[0].date() and (d.hour or d.minute)]
            dates = precises or dates
        dates = dates or toutes_dates(description)
        heures = set(_HEURE.findall(description))
        if len(dates) == 1 and not (dates[0].hour or dates[0].minute) and len(heures) == 1:
            # « Le mardi 20 octobre 2026 à l'IRMC (17h30) » : une seule heure dans le texte
            h, mn = heures.pop()
            dates = [dates[0].replace(hour=int(h), minute=int(mn))]
        if not titre or not dates:
            continue
        if opts.get("garder") and not re.search(opts["garder"], f"{titre} {description}", re.I):
            continue
        if opts.get("nettoyer_titre"):
            titre = propre(re.sub(opts["nettoyer_titre"], "", titre))
        e = Evenement(titre=titre, debut=dates[0], fin=dates[-1] if len(dates) > 1 else None,
                      lien=propre(el["lien"]) or source["url"], lieu=lieu, description=resume(description))
        if opts.get("lire_page") and el["lien"]:
            _completer(e, el["lien"])
        res.append(e)
    return res


def _completer(e: Evenement, lien: str) -> None:
    try:
        texte = BeautifulSoup(telecharger(lien), "html.parser").get_text("\n")
    except Exception as exc:  # noqa: BLE001 — la page manque : on garde ce que dit le flux
        print(f"  page illisible {lien} ({exc})")
        return
    d = details_page(texte)
    e.lieu = d.get("lieu") or e.lieu
    # la plage de dates ne compte que si elle contient la date du flux (sinon c'est un autre événement cité)
    if d.get("debut") and d["debut"].date() <= e.debut.date() <= d["fin"].date():
        heure = dict(hour=e.debut.hour, minute=e.debut.minute)
        e.debut, e.fin = d["debut"].replace(**heure), d["fin"]


def recuperer(source: dict) -> list[Evenement]:
    xml = telecharger(source["url"])
    if not elements(xml):
        raise RuntimeError("flux vide ou illisible")
    return depuis_flux(xml, source)
