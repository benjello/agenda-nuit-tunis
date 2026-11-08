"""Films à l'affiche de tunis.events : un seul site pour plusieurs salles de Tunis.

tunis.events (billetterie) publie sur https://tunis.events/cinema les films de
plusieurs salles (Colisée, Palace, CinéMadart, Agora, Pathé…) en schema.org :
un objet par film, par salle et par jour, avec le lien vers la réservation.
C'est aussi le seul moyen de lire Pathé, dont le site bloque GitHub.

Résultat : un événement par film et par salle (catégorie cinéma), avec ses séances
(jour et heure). Les salles hors Grand Tunis sont écartées.

Options :
  exclure   mots qui écartent une salle (défaut : Sousse, Sfax, Nabeul, Bizerte…)
"""
from __future__ import annotations

from ..commun import Evenement, film, json_ld_evenements, page, propre, slug
from .jsonld import _date, _lieu

EXCLURE = ("sousse", "sfax", "nabeul", "hammamet", "bizerte", "monastir", "djerba", "kairouan", "gabes")


def _image(v):
    if isinstance(v, list):
        v = v[0] if v else None
    if isinstance(v, dict):
        v = v.get("url")
    return v if isinstance(v, str) else ""


def recuperer(source: dict) -> list[Evenement]:
    exclure = tuple(m.lower() for m in source.get("options", {}).get("exclure", EXCLURE))
    films: dict[tuple, dict] = {}
    for o in json_ld_evenements(page(source["url"])):
        debut, titre = _date(o.get("startDate")), propre(o.get("name"))
        lieu, adresse = _lieu(o.get("location") or {})
        if not (debut and titre and lieu) or any(m in f"{lieu} {adresse}".lower() for m in exclure):
            continue
        # « WEEKEND » et « Weekend » dans la même salle : un seul film.
        f = films.setdefault((slug(lieu), slug(titre)), {
            "titre": titre, "lien": o.get("url") or source["url"], "lieu": lieu,
            "adresse": adresse, "image": _image(o.get("image")), "jours": set()})
        # un objet par séance ; minuit = séance sans horaire connu (on garde le jour seul)
        f["jours"].add(f"{debut:%Y-%m-%d %H:%M}" if (debut.hour or debut.minute) else debut.date().isoformat())
    if not films:
        raise RuntimeError("aucun film en schema.org sur la page (site modifié ?)")
    return [film(f["titre"], f["lien"], f["lieu"], f["jours"], f["adresse"], image=f["image"])
            for f in films.values()]

