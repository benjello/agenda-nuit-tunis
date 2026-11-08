"""Scraper générique « liste + fiches ».

Pour un site qui a une page de programme avec des liens vers une fiche par
événement, chaque fiche donnant ses dates en clair (« 07 Novembre 2026 à 19:30 »
ou « 26.09.2026 »).

Options :
  motif : morceau d'adresse commun aux fiches (ex. « /fr/programme/ », « details-agenda »)
  lieu  : nom du lieu, si les fiches ne le donnent pas
"""
from __future__ import annotations

import datetime as dt
import re
import time
from urllib.parse import urljoin

from ..commun import Evenement, json_ld_evenements, meta, page, propre, toutes_dates
from .jsonld import depuis_json_ld


def liens_fiches(soup, base: str, motif: str) -> list[str]:
    vus = []
    for a in soup.find_all("a", href=True):
        if motif not in a["href"]:
            continue
        url = urljoin(base, a["href"]).split("#")[0]
        if url not in vus and url.rstrip("/") != base.rstrip("/"):
            vus.append(url)
    return vus


_RE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?")


def dates_iso(corps) -> list[dt.datetime]:
    """Dates au format ISO (« 2026-11-07 », « 2026-11-07T19:30 ») : dans le texte ou une balise <time datetime>."""
    res = []
    for m in _RE_ISO.findall(corps.get_text(" ")):
        try:
            res.append(dt.datetime(int(m[0]), int(m[1]), int(m[2]), int(m[3] or 0), int(m[4] or 0)))
        except ValueError:
            continue
    for t in corps.find_all("time", attrs={"datetime": True}):
        for m in _RE_ISO.findall(t["datetime"]):
            try:
                res.append(dt.datetime(int(m[0]), int(m[1]), int(m[2]), int(m[3] or 0), int(m[4] or 0)))
            except ValueError:
                continue
    return sorted(set(res))


def lire_fiche(soup, url: str, lieu: str, aujourd_hui: dt.datetime) -> Evenement | None:
    ld = [e for e in depuis_json_ld(json_ld_evenements(soup), url) if (e.fin or e.debut) >= aujourd_hui]
    if ld:
        e = ld[0]
        e.lieu = e.lieu or lieu
        return e
    titre = propre((soup.find("h1") or soup.find("h2") or soup.new_tag("x")).get_text(" ")) or meta(soup, "og:title")
    titre = re.sub(r"\s*(::|\|\s*Institut|–\s*Institut).*$", "", titre)
    corps = soup.find("main") or soup.find("article") or soup
    dates = [d for d in toutes_dates(corps.get_text(" ")) + dates_iso(corps) if d >= aujourd_hui]
    dates = sorted(set(dates))
    if not titre or not dates:
        # Journal de l'exécution : une fiche rejetée doit se voir (sinon une source reste à 0 sans explication).
        print(f"    fiche ignorée (titre : {bool(titre)}, date à venir : {bool(dates)}) : {url}")
        return None
    prix = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:DT|TND)\b", corps.get_text(" "))
    return Evenement(titre=titre, debut=dates[0], fin=dates[-1] if len(dates) > 1 else None,
                     seances=dates, lien=url, lieu=lieu,
                     prix=f"{prix.group(1).replace('.000', '')} DT" if prix else "")


def recuperer(source: dict, motif_defaut: str = "") -> list[Evenement]:
    opts = source.get("options") or {}
    motif = opts.get("motif", motif_defaut)
    if not motif:
        raise ValueError("option « motif » manquante")
    lieu = opts.get("lieu", source["nom"])
    aujourd_hui = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    liens = liens_fiches(page(source["url"]), source["url"], motif)
    if not liens:
        raise RuntimeError(f"aucun lien contenant « {motif} » sur la page de programme "
                           "(liste chargée en JavaScript, ou site modifié ?)")
    evenements = []
    for url in liens:
        try:
            e = lire_fiche(page(url), url, lieu, aujourd_hui)
            if e:
                evenements.append(e)
        except Exception:  # noqa: BLE001 — une fiche illisible n'arrête pas les autres
            continue
        time.sleep(0.5)
    return evenements
