"""Lance les scrapers des sources actives et met à jour le site.

Usage :
  python3 -m scrapers                 toutes les sources actives
  python3 -m scrapers teskerti        une ou plusieurs sources, par id
  python3 -m scrapers --debug         garde les pages téléchargées dans debug/

Si un scraper échoue, les événements déjà récupérés pour cette source sont gardés :
une panne ne vide jamais le site. Le résultat de chaque source est noté dans
_data/etat_sources.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import sys
import traceback

import yaml

from . import commun
from .commun import RACINE, EnAttente
from . import controle, doublons, festivals, films
from .ecriture import STATS_HORAIRE, ecrire, ecrire_etat, lire_etat


def charger_sources() -> list[dict]:
    return yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []


def lancer(source: dict):
    module = importlib.import_module(f".sources.{source['scraper']}", __package__)
    return module.recuperer(source)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ids", nargs="*", help="ids des sources à lancer (par défaut : toutes les actives)")
    p.add_argument("--debug", action="store_true", help="garder les pages téléchargées dans debug/")
    args = p.parse_args(argv)
    if args.debug:
        commun.DEBUG_DIR = RACINE / "debug"

    sources = [s for s in charger_sources() if (s["id"] in args.ids if args.ids else s.get("actif", True))]
    if args.ids and len(sources) < len(set(args.ids)):
        print(f"Sources inconnues : {set(args.ids) - {s['id'] for s in sources}}", file=sys.stderr)
    etat = lire_etat()
    maintenant = dt.datetime.now().isoformat(timespec="seconds")
    echecs = 0
    attentes = sautees = 0
    for s in sources:
        e = etat.setdefault(s["id"], {})
        # Sources payantes ou lentes (Facebook) : relues seulement tous les N jours.
        tous_les = s.get("tous_les_jours")
        if tous_les and not args.ids and e.get("ok") and e.get("dernier_succes"):
            ecart = dt.datetime.now() - dt.datetime.fromisoformat(e["dernier_succes"])
            if ecart < dt.timedelta(days=tous_les, hours=-2):
                print(f"· {s['id']} : relue il y a {ecart.days} j, prochaine lecture plus tard")
                sautees += 1
                continue
        e["dernier_passage"] = maintenant
        e.setdefault("premier_passage", maintenant)  # point de départ du délai « silencieuse »
        try:
            resultat = lancer(s)
            # Une liste vide n'est pas une panne : la source peut n'avoir rien à venir.
            # Les scrapers lèvent une erreur quand la page elle-même est méconnaissable.
            n = ecrire(s, resultat)
            e.update(ok=True, nb=n, erreur=None, attente=None, dernier_succes=maintenant)
            if s["id"] in STATS_HORAIRE and STATS_HORAIRE[s["id"]][0]:
                e["sans_heure"] = STATS_HORAIRE[s["id"]][0] - STATS_HORAIRE[s["id"]][1]
                print(f"  heures : {STATS_HORAIRE[s['id']][1]}/{STATS_HORAIRE[s['id']][0]} événement(s) avec une heure")
            else:
                e.pop("sans_heure", None)
            if n:  # page « Santé des sources » : depuis quand la source n'a plus rien annoncé
                e["dernier_non_vide"] = maintenant
            print(f"✓ {s['id']} : {n}")
        except EnAttente as exc:
            attentes += 1
            e.update(attente=str(exc)[:300])
            print(f"… {s['id']} : en attente ({exc})")
        except Exception as exc:  # noqa: BLE001 — une source en panne ne doit pas arrêter les autres
            echecs += 1
            e.update(ok=False, erreur=f"{type(exc).__name__}: {exc}"[:300])
            print(f"✗ {s['id']} : {e['erreur']}", file=sys.stderr)
            if args.debug:
                traceback.print_exc()
    ecrire_etat(etat)
    n = doublons.marquer(charger_sources())
    nfest = festivals.rattacher(yaml.safe_load((RACINE / "_data" / "festivals.yml").read_text()) or [],
                                series=yaml.safe_load((RACINE / "_data" / "series.yml").read_text()) or [])
    nf = films.ecrire()
    controle.main()
    print(f"{len(sources) - echecs}/{len(sources)} sources à jour, {n} doublon(s) masqué(s), {nfest} événement(s) relié(s) à un festival ou une série, {nf} film(s) à l'affiche.")
    essais = len(sources) - attentes - sautees
    return 1 if essais and echecs == essais else 0


if __name__ == "__main__":
    sys.exit(main())
