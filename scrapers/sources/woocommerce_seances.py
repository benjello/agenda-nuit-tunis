"""Billetterie WordPress + WooCommerce d'un cinéma (L'Agora, La Marsa : lagora.tn).

Chaque film est un « produit » ; ses séances sont les valeurs de l'attribut « Séances »,
écrites comme « Dim. 1 novembre - 15:00 - VF ». On les lit par l'API publique de
WooCommerce (/wp-json/wc/store/v1/products), sans compte : titres, séances, prix,
affiche et résumé.

Options :
  lieu       nom du lieu
  adresse    adresse du lieu
  attribut   nom de l'attribut des séances (défaut « Séances »)
"""
from __future__ import annotations

import datetime as dt
import html
import re

from ..commun import MOIS, Evenement, categorie_du_titre, film, propre, resume, telecharger_json

_SEANCE = re.compile(r"(?:\b(lun|mar|mer|jeu|ven|sam|dim)\w*\.?\s+)?(\d{1,2})(?:er)?\s+([a-zéûè]+)\.?\s*(?:(\d{4}))?"
                     r"\s*-\s*(\d{1,2})[:hH](\d{2})", re.I)
_JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
_PAS_FILM = re.compile(r"pi[èe]ce de th[ée][âa]tre|\bth[ée][âa]tre\b|spectacle|concert|stand.?up|one.?(?:wo)?man.?show|"
                       r"humour|conf[ée]rence|atelier", re.I)


def _texte(v: str) -> str:
    return propre(re.sub(r"<[^>]+>", " ", html.unescape(v or "")))


def seances(termes: list[str], aujourd_hui: dt.date) -> list[str]:
    """« Dim. 1 novembre - 15:00 - VF » → « 2026-11-01 15:00 ». L'année manque : la plus proche."""
    res = []
    for t in termes:
        m = _SEANCE.search(t)
        if not m or m.group(3).lower() not in MOIS:
            continue
        mois, jour = MOIS[m.group(3).lower()], int(m.group(2))
        # L'année n'est pas écrite : celle où le jour de la semaine (« Dim. ») tombe juste,
        # parmi l'année passée, celle-ci et la suivante ; sinon la date la plus proche.
        annees = [int(m.group(4))] if m.group(4) else [aujourd_hui.year - 1, aujourd_hui.year, aujourd_hui.year + 1]
        possibles = []
        for a in annees:
            try:
                d = dt.datetime(a, mois, jour, int(m.group(5)), int(m.group(6)))
            except ValueError:
                continue
            if not m.group(1) or _JOURS[d.weekday()] == m.group(1).lower():
                possibles.append(d)
        if not possibles:
            continue
        d = min(possibles, key=lambda x: abs((x.date() - aujourd_hui).days))
        res.append(f"{d:%Y-%m-%d %H:%M}")
    return res


def _prix(p: dict) -> str:
    prix = (p.get("prices") or {})
    try:
        v = int(prix.get("price") or 0) / 10 ** int(prix.get("currency_minor_unit") or 0)
    except (TypeError, ValueError):
        return ""
    if p.get("is_in_stock") is False:
        return f"{v:g} DT · Complet" if v else "Complet"
    return f"{v:g} DT" if v else ""


def depuis_produits(produits: list[dict], source: dict, aujourd_hui: dt.date | None = None) -> list:
    o = source.get("options") or {}
    aujourd_hui = aujourd_hui or dt.date.today()
    nom_attr = o.get("attribut", "Séances").lower()
    res = []
    for p in produits:
        attr = next((a for a in p.get("attributes") or [] if (a.get("name") or "").lower() == nom_attr), None)
        if not attr:
            continue
        limite = (aujourd_hui + dt.timedelta(days=120)).isoformat()
        jours = [j for j in seances([t.get("name", "") for t in attr.get("terms") or []], aujourd_hui)
                 if aujourd_hui.isoformat() <= j[:10] <= limite]
        titre = _texte(p.get("name"))
        if not jours or not titre:
            continue
        images = p.get("images") or []
        resume_p = resume(_texte(p.get("description") or p.get("short_description")))
        if _PAS_FILM.search(titre):  # la billetterie vend aussi des pièces et des concerts
            debuts = sorted(dt.datetime.fromisoformat(j) for j in jours)
            res.append(Evenement(titre=titre, debut=debuts[0], lien=p.get("permalink") or source["url"],
                                 lieu=o.get("lieu", source["nom"]), adresse=o.get("adresse", ""),
                                 categorie=categorie_du_titre(titre) or "theatre", prix=_prix(p),
                                 seances=debuts if len(debuts) > 1 else [],
                                 image=(images[0].get("src") or "") if images else "", description=resume_p))
            continue
        e = film(titre, p.get("permalink") or source["url"], o.get("lieu", source["nom"]), jours,
                 o.get("adresse", ""), image=(images[0].get("src") or "") if images else "",
                 prix=_prix(p), description=resume_p)
        if e:
            res.append(e)
    return res


def recuperer(source: dict) -> list:
    base = source["url"].rstrip("/")
    produits, page = [], 1
    while page <= 5:
        lot = telecharger_json(f"{base}/wp-json/wc/store/v1/products?per_page=100&page={page}")
        if not isinstance(lot, list):
            raise RuntimeError("réponse WooCommerce inattendue")
        produits += lot
        if len(lot) < 100:
            break
        page += 1
    if not produits:
        raise RuntimeError("aucun produit dans la billetterie")
    return depuis_produits(produits, source)
