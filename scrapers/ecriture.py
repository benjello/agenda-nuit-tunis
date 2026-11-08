"""Écrit le résultat d'un scraper dans le site.

- Événements : un fichier Markdown par événement dans _events/auto/<source>/,
  exactement comme ceux saisis à la main. Le dossier est réécrit à chaque passage.
  Les films à l'affiche sont des événements comme les autres (catégorie cinéma,
  « film: true », une séance par jour de projection).
- Programmes publiés en image (affiches) : _data/programmes/<source>.json.
- État des sources : _data/etat_sources.json (dernier passage, succès, nombre d'événements).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil

from .commun import RACINE, Evenement, Publication, categorie_nuit, est_discret, est_famille, horaire_du_texte, pas_un_evenement, retours_ligne_casses, slug, titre_film
from .pages import _cle, faux_lieux
from .villes import mention, ville

DOSSIER_AUTO = RACINE / "_events" / "auto"
DOSSIER_PROGRAMMES = RACINE / "_data" / "programmes"
FICHIER_ETAT = RACINE / "_data" / "etat_sources.json"


LIEU_INCONNU = "Lieu à préciser"
# Par source : (événements écrits, dont avec une heure). Lu par __main__ pour l'état des sources.
STATS_HORAIRE: dict[str, tuple[int, int]] = {}


def _yaml(v) -> str:
    # Une chaîne JSON est aussi une chaîne YAML valide : pas de souci d'apostrophes ou de « : ».
    return json.dumps(v, ensure_ascii=False, default=str)


def _texte_brut(t: str) -> str:
    """La notice vient d'ailleurs : on neutralise le Markdown (titres, listes) et le Liquid."""
    t = re.sub(r"[{}<>]", "", retours_ligne_casses(t))
    return "\n".join("\\" + l.lstrip() if re.match(r"\s*(#|[>*+=-]|\d+\.\s)", l) else l
                      for l in t.split("\n"))


def _date(d: dt.datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M") if (d.hour or d.minute) else d.strftime("%Y-%m-%d")


def _heure(h: tuple[int, int]) -> str:
    return f"{h[0]:02d}:{h[1]:02d}"


def completer_horaire(e: Evenement) -> str | None:
    """Complète l'heure de début (dans e.debut) et renvoie l'heure de fin « HH:MM » : celles de la source,
    sinon celles que dit la notice ou le titre. Pas d'heure inventée : sans indice, l'événement reste « sans heure »."""
    sans_heure = not (e.debut.hour or e.debut.minute)
    un_jour = not e.seances and (not e.fin or e.fin.date() == e.debut.date())
    if sans_heure and un_jour and not e.film and e.categorie != "expo":
        debut, fin = horaire_du_texte(f"{e.titre}\n{e.description}")
        if debut:
            e.debut = e.debut.replace(hour=debut[0], minute=debut[1])
            if fin:
                e.fin = e.debut.replace(hour=fin[0], minute=fin[1])
    if sans_heure and not (e.debut.hour or e.debut.minute):
        return None
    if not e.fin or not (e.fin.hour or e.fin.minute) or e.seances:
        return None
    if e.fin.date() == e.debut.date() and e.fin > e.debut:
        return _heure((e.fin.hour, e.fin.minute))
    if e.fin.date() == e.debut.date() + dt.timedelta(days=1) and e.fin.hour < 8:
        return _heure((e.fin.hour, e.fin.minute))  # soirée qui finit après minuit
    return None


def ecrire(source: dict, resultat: list) -> int:
    """Range le résultat d'un scraper : événements et programmes (affiches)."""
    evenements = [x for x in resultat if isinstance(x, Evenement)]
    publications = [x for x in resultat if isinstance(x, Publication)]
    if publications or source.get("scraper") == "facebook_programmes":
        ecrire_publications(source, publications)
    n = ecrire_evenements(source, evenements)
    return n if evenements or not publications else len(publications)


def ecrire_evenements(source: dict, evenements: list[Evenement]) -> int:
    aujourd_hui = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for e in evenements:  # séances passées retirées : l'événement commence à la prochaine
        if e.seances:
            e.seances = [s for s in e.seances if s >= aujourd_hui] or e.seances
            e.debut = e.seances[0]
    # Granularité : une annonce de service (« la Médiathèque ouvre exceptionnellement ») n'est pas un événement,
    # et un film s'affiche sous son titre, sans la rubrique (« Movie Night: UN FILS » → « UN FILS »).
    a_venir = [e for e in evenements if (e.fin or e.debut) >= aujourd_hui and not pas_un_evenement(e.titre)]
    # Agenda de la nuit : on ne garde que les sorties du soir (club, cabaret, concert…), avec leur catégorie.
    # Films, expos, conférences, ateliers et pièces de théâtre restent dans l'agenda culturel.
    for e in a_venir:
        e.categorie = categorie_nuit(e.categorie or source.get("categorie") or "autre", e.titre)
    a_venir = [e for e in a_venir if e.categorie and not e.film]
    for e in a_venir:
        if e.film or e.categorie == "cinema":
            e.titre = titre_film(e.titre)
    dossier = DOSSIER_AUTO / source["id"]
    # « Nouveau cette semaine » : on garde la date où l'événement est apparu la première fois.
    deja = {}
    if dossier.exists():
        for f in dossier.glob("*.md"):
            m = re.search(r"^ajoute: \"?(\d{4}-\d{2}-\d{2})", f.read_text(), re.M)
            if m:
                deja[f.stem] = m.group(1)
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)
    vus = set()
    total = avec_heure = 0
    faux = faux_lieux([source])
    defaut = (source.get("options") or {}).get("lieu") or source["nom"]
    for e in a_venir:
        nom = f"{e.debut:%Y-%m-%d}-{slug(e.titre)[:60]}"
        if nom in vus:  # même titre le même jour, dans un autre lieu
            nom += "-" + slug(e.lieu)[:30]
        if nom in vus:
            continue
        vus.add(nom)
        lieu = e.lieu or source["nom"]
        if _cle(lieu) in faux:  # « Webdo », « Kadhem » : la source, pas un lieu
            lieu = LIEU_INCONNU
        if lieu in (defaut, LIEU_INCONNU) and not e.adresse:
            # Lieu par défaut de la source, mais l'annonce parle d'une autre ville :
            # « Direction Gabès pour les Oasis Days ! » chez La Boîte (Tunis) → Gabès.
            ailleurs = mention(e.titre)
            if ailleurs and ailleurs[0] != ville(lieu if lieu != LIEU_INCONNU else source["nom"]):
                lieu = f"{ailleurs[1]}, voir l'annonce"
        fin_heure = completer_horaire(e)
        if not (e.film or e.categorie == "expo"):  # films et expos : séances ou ouverture, pas une heure d'événement
            total += 1
            avec_heure += bool(e.debut.hour or e.debut.minute or e.seances)
        champs = {
            "title": e.titre,
            "date": _date(e.debut),
            "end_time": fin_heure,
            "end_date": _date(e.fin) if e.fin and e.fin.date() != e.debut.date() and not fin_heure else None,
            "venue": lieu,
            "address": e.adresse or None,
            "ville": ville(lieu if lieu != LIEU_INCONNU else source["nom"], e.adresse),
            "category": e.categorie or source.get("categorie") or "autre",
            "price": e.prix or None,
            "link": e.lien,
            "source": source["id"],
            "source_name": source["nom"],
            "seances": [_date(s) for s in e.seances] if len(e.seances) > 1 else None,
            "image": e.image or None,
            "film": True if e.film else None,
            "imdb": e.imdb or None,
            "duration": e.duree or None,
            "genres": e.genres or None,
            "article_titre": e.article or None,
            "festival": e.festival or None,
            "artists": e.artistes or None,
            "discret": True if est_discret(e.titre) else None,
            "famille": True if est_famille(e.titre, e.description) else None,
            "ajoute": deja.get(nom) or dt.date.today().isoformat(),
        }
        lignes = ["---"] + [f"{k}: {_yaml(v)}" for k, v in champs.items() if v is not None]
        lignes += ["auto: true", "---", ""]
        if e.description:  # notice, affichée sur la fiche de l'événement (texte brut, pas de Markdown)
            lignes += [_texte_brut(e.description), ""]
        # Le nom de fichier commence par la date ; on force la date complète dans le front matter.
        (dossier / f"{nom}.md").write_text("\n".join(lignes).replace(
            f'date: "{champs["date"]}"', f'date: {champs["date"]}'))
    STATS_HORAIRE[source["id"]] = (total, avec_heure)
    return len(vus)


def ecrire_publications(source: dict, publications: list[Publication]) -> int:
    DOSSIER_PROGRAMMES.mkdir(parents=True, exist_ok=True)
    data = {
        "id": source["id"], "nom": source["nom"], "url": source["url"],
        "mis_a_jour": dt.date.today().isoformat(),
        "publications": [p.en_dict() for p in publications],
    }
    (DOSSIER_PROGRAMMES / f"{source['id']}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    return len(publications)


def lire_etat() -> dict:
    try:
        return json.loads(FICHIER_ETAT.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def ecrire_etat(etat: dict) -> None:
    FICHIER_ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
