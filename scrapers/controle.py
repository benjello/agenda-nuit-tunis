"""Contrôle des événements écrits par les scrapers, après chaque passage.

Corrige ce qui est sûr :
- un lieu qui est en fait le nom de la source (« Webdo », « Kadhem ») → « Lieu à préciser » ;
- un code Google Maps collé au lieu (« Grafiflow V7JH+6J7 » → « Grafiflow ») ;
- une annonce de service (« la Médiathèque ouvre exceptionnellement… ») → retirée ;
- une annonce de partenariat (« fier d'être partenaire de la 8e édition de… ») → masquée ;
- une rubrique devant le titre d'un film (« Movie Night: UN FILS » → « UN FILS »).
  Utile pour les sources qui ne sont pas relues chaque jour (Instagram, Facebook).

Signale le reste dans _data/controle.json, affiché sur la page « État des sources » :
titre trop vague ou trop long (début d'une légende), date très lointaine, fin avant le
début, même événement deux fois dans une source, et ce qui rend une entrée imprécise
(voir scrapers/granularite.py : titre générique, lien vers une page générale, film sans séance…).
Le bilan de granularité par source et par type de scraper va aussi dans _data/controle.json.

  python3 -m scrapers.controle
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import yaml

from .commun import RACINE, annonce_de_partenariat, pas_un_evenement, titre_film
from .doublons import _ecrire, _lire
from .ecriture import DOSSIER_AUTO, LIEU_INCONNU
from .granularite import A_SIGNALER, DEFAUTS, bilan
from .pages import _cle, faux_lieux

FICHIER = RACINE / "_data" / "controle.json"
_PLUS_CODE = re.compile(r"\s*\b[23456789CFGHJMPQRVWX]{4,6}\+[23456789CFGHJMPQRVWX]{2,3}\b")
_VAGUES = re.compile(r"^(?:exposition|expo|soir[ée]e|concert|spectacle|[ée]v[ée]nement|programme|agenda|atelier|"
                     r"conf[ée]rence|rencontre|projection|tables? rondes?|nouveau|bient[ôo]t|save the date|"
                     r"coming soon|stay tuned|à venir)\W*$", re.I)
TITRE_MAX = 85      # au-delà, c'est presque toujours le début d'une légende Instagram
JOURS_MAX = 180


def problemes(c: dict, aujourd_hui: dt.date, presse: bool = False) -> list[str]:
    res = []
    titre = str(c.get("title") or "").strip()
    if len(re.findall(r"[^\W\d_]", titre)) < 3:
        res.append("titre vide ou illisible")
    elif _VAGUES.match(titre):
        res.append("titre trop vague")
    elif len(titre) >= TITRE_MAX and not presse:  # un titre d'article est long
        res.append("titre trop long (début d'une légende ?)")
    try:
        debut = dt.date.fromisoformat(str(c.get("date"))[:10])
    except ValueError:
        return res + ["date illisible"]
    if (debut - aujourd_hui).days > JOURS_MAX:
        res.append(f"date lointaine ({debut:%d/%m/%Y})")
    if c.get("end_date"):
        try:
            if dt.date.fromisoformat(str(c["end_date"])[:10]) < debut:
                res.append("fin avant le début")
        except ValueError:
            res.append("date de fin illisible")
    return res


def controler(sources: list[dict], dossier: Path = DOSSIER_AUTO, aujourd_hui: dt.date | None = None) -> dict:
    aujourd_hui = aujourd_hui or dt.date.today()
    faux = faux_lieux(sources)
    genres = {s["id"]: s.get("genre") for s in sources}
    corriges, signales, vus, entrees = 0, [], {}, []
    for f in sorted(dossier.glob("*/*.md")):
        champs, corps = _lire(f)
        if not champs:
            continue
        if not isinstance(champs.get("date"), str):
            champs["date"] = str(champs.get("date"))[:16]
        titre = str(champs.get("title") or "")
        if pas_un_evenement(titre):
            f.unlink()
            corriges += 1
            continue
        lieu = str(champs.get("venue") or "")
        nouveau = _PLUS_CODE.sub("", lieu).strip(" ,")
        if _cle(nouveau) in faux:
            nouveau = LIEU_INCONNU
        film = titre_film(titre) if (champs.get("film") or champs.get("category") == "cinema") else titre
        if nouveau != lieu or film != titre:
            champs["venue"], champs["title"] = nouveau, film
            auto = champs.pop("auto", True)
            champs["auto"] = auto
            _ecrire(f, champs, corps)
            corriges += 1
        if annonce_de_partenariat(corps or "") and not champs.get("doublon"):
            champs["doublon"] = True  # masquée : un partenariat n'est pas un événement
            champs["partenariat"] = True
            if not isinstance(champs.get("date"), str):
                champs["date"] = str(champs.get("date"))[:16]
            auto = champs.pop("auto", True)
            champs["auto"] = auto
            _ecrire(f, champs, corps)
            corriges += 1
        if not champs.get("doublon"):
            entrees.append((f, champs, corps or ""))
    gran = bilan([(dict(c, _fichier=f.name), corps) for f, c, corps in entrees], sources)
    for f, champs, _ in entrees:
        liste = problemes(champs, aujourd_hui, genres.get(champs.get("source")) == "presse")
        liste += [DEFAUTS[c] for c in gran["evenements"].get((champs.get("source"), f.name), []) if c in A_SIGNALER]
        cle = (champs.get("source"), str(champs["date"])[:10], _cle(str(champs.get("title")))[:40],
               _cle(str(champs.get("venue")))[:15])
        if cle in vus:
            liste.append(f"deux fois dans la source (voir {vus[cle]})")
        vus.setdefault(cle, f.name)
        if liste:
            signales.append({"fichier": f"{f.parent.name}/{f.name}", "source": champs.get("source"),
                             "titre": str(champs.get("title"))[:100], "date": str(champs["date"])[:10],
                             "lien": champs.get("link"), "problemes": liste})
    rapport = {"date": aujourd_hui.isoformat(), "corriges": corriges, "a_verifier": signales,
               "granularite": {"sources": gran["sources"], "scrapers": gran["scrapers"]}}
    return rapport


def main() -> int:
    sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()) or []
    r = controler(sources)
    FICHIER.write_text(json.dumps(r, ensure_ascii=False, indent=1) + "\n")
    print(f"Contrôle : {r['corriges']} lieu(x) corrigé(s), {len(r['a_verifier'])} entrée(s) à vérifier")
    for k, v in r["granularite"]["scrapers"].items():
        print(f"  granularité {k} : {v['pourcent']} % d'événements précis sur {v['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
