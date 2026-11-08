"""Consommation du crédit Apify (Instagram, Facebook) : _data/apify.json et alerte.

Lit https://api.apify.com/v2/users/me/limits avec APIFY_TOKEN. Écrit la dépense du mois
dans _data/apify.json (affichée sur la page Santé) et, à partir de SEUIL % de la limite,
imprime le texte d'une alerte en Markdown (le workflow en fait un ticket GitHub).

  python3 -m scrapers.credit_apify > alerte-apify.md
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import requests

from .commun import RACINE

FICHIER = RACINE / "_data" / "apify.json"
SEUIL = 80


def lire(token: str) -> dict:
    r = requests.get("https://api.apify.com/v2/users/me/limits", params={"token": token}, timeout=30)
    r.raise_for_status()
    d = r.json().get("data") or {}
    depense = float((d.get("current") or {}).get("monthlyUsageUsd") or 0)
    limite = float((d.get("limits") or {}).get("maxMonthlyUsageUsd") or 0)
    cycle = d.get("monthlyUsageCycle") or {}
    return {"jour": dt.date.today().isoformat(), "depense": round(depense, 2), "limite": round(limite, 2),
            "pourcent": round(100 * depense / limite) if limite else None,
            "fin_cycle": str(cycle.get("endAt") or "")[:10]}


def alerte(c: dict) -> str:
    if c.get("pourcent") is None or c["pourcent"] < SEUIL:
        return ""
    etat = "épuisé" if c["pourcent"] >= 100 else "presque épuisé"
    return (f"Le crédit Apify du mois est **{etat}** : {c['depense']} $ sur {c['limite']} $ ({c['pourcent']} %).\n\n"
            f"Tant qu'il n'est pas rechargé, les comptes Instagram et les pages Facebook ne sont plus lus "
            f"(les sites, flux RSS et journaux continuent).\n\n"
            f"Recharge du crédit : {c['fin_cycle'] or 'voir la console Apify, Billing'}. "
            f"Pour en avoir plus : plan Starter (console Apify, Billing).\n\n"
            f"Ce ticket se ferme tout seul quand la consommation repasse sous {SEUIL} %.\n")


def main() -> int:
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("pas de APIFY_TOKEN", file=sys.stderr)
        return 0
    try:
        c = lire(token)
    except (requests.RequestException, ValueError) as exc:
        print(f"crédit Apify illisible : {exc}", file=sys.stderr)
        return 0
    FICHIER.write_text(json.dumps(c, ensure_ascii=False, indent=1) + "\n")
    print(f"Apify : {c['depense']} $ sur {c['limite']} $ ({c['pourcent']} %)", file=sys.stderr)
    sys.stdout.write(alerte(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
