"""Teskerti (teskerti.tn), billetterie en ligne.

Couvre de nombreux lieux de Tunis qui n'ont pas de site : Théâtre municipal,
4ème Art, Le Rio, salle Africa, Ciné Alhambra Zéphyr…

1. La page d'accueil donne la liste des catégories (/category/<nom>).
2. Chaque catégorie donne ses événements (/evenement/<nom>).
3. Chaque fiche donne la date, l'heure, le lieu et le prix.

Options (facultatives) :
  categories_exclues : catégories ignorées (par défaut : sport, professionnel)
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin

from ..commun import Evenement, dates_fr, json_ld_evenements, meta, page, propre, slug
from .jsonld import depuis_json_ld

BASE = "https://teskerti.tn/"
EXCLUES = {"sport", "professionnel"}
# Rubriques de Teskerti → catégories de l'agenda de la nuit. Cinéma, théâtre et spectacles
# (jeune public surtout) n'en sont pas : scrapers/ecriture.py les écarte, sauf titre de soirée (« DJ », « cabaret »).
CATEGORIES = {"cinema": "cinema", "spectacle": "theatre", "theatre": "theatre",
              "concert": "concert", "musique": "concert", "clubbing": "club", "soiree": "club", "festival": "festival",
              "saisons-de-la-creation": "theatre", "humour": "humour", "stand-up": "humour"}
MOTS_LIEU = re.compile(r"\b(th[ée]âtre|theatre|salle|cin[ée]|cinema|espace|cit[ée]|centre|"
                       r"maison|club|h[ôo]tel|resort|palais|dar|rio|art|op[ée]ra|galerie|"
                       r"institut|zephyr|zéphyr|th[ée]atre)\b", re.I)


def liens(soup, motif: str) -> list[tuple[str, str]]:
    """(adresse absolue, texte) des liens dont l'adresse contient motif, sans doublons."""
    vus, res = set(), []
    for a in soup.find_all("a", href=True):
        url = urljoin(BASE, a["href"]).split("#")[0].split("?")[0]
        if motif in url and url not in vus:
            vus.add(url)
            res.append((url, propre(a.get_text(" "))))
    return res


# Liens de menu qui ressemblent à des noms de lieux : « Espace pro », « Mon espace »…
FAUX_LIEUX = re.compile(r"^(mon |votre )?espace (pro|client|organisateur|membre)s?$|^mon espace$|teskerti", re.I)


def _est_lieu(ligne: str) -> bool:
    return (3 < len(ligne) < 90 and ligne[:1].isupper() and bool(MOTS_LIEU.search(ligne))
            and not FAUX_LIEUX.search(ligne) and not dates_fr(ligne))


def _separer(ligne: str) -> tuple[str, str]:
    """« Théâtre Le 4ème Art : 7 Av. de Paris » → (lieu, adresse)."""
    lieu, _, adresse = ligne.partition(" : ")
    return propre(lieu), propre(adresse)


def lieu_de_la_fiche(soup, titre: str = "") -> tuple[str, str]:
    # On garde toute la page : sur teskerti.tn, le bloc titre + lieu peut être dans un <header>.
    # Les liens de menu (« Espace pro »…) sont écartés par FAUX_LIEUX.
    corps = soup.body or soup
    for el in corps.find_all(["script", "style", "noscript"]):
        el.decompose()
    lignes = [propre(x) for x in corps.get_text("\n").split("\n") if propre(x)]
    # Un élément dont la classe désigne un lieu (le plus fiable quand il existe)
    for el in corps.find_all(class_=re.compile(r"(^|[-_])(lieu|venue|location|salle|adresse|address)([-_]|$)", re.I)):
        t = propre(el.get_text(" "))
        if 2 < len(t) < 120:
            lignes_el = [propre(x) for x in el.get_text("\n").split("\n") if propre(x)]
            return _separer(lignes_el[0])[0], ", ".join(lignes_el[1:2]) or _separer(lignes_el[0])[1]
    # Sur teskerti.tn, la ligne qui suit le titre est « Lieu : adresse ».
    if titre and titre in lignes:
        i = lignes.index(titre)
        for ligne in lignes[i + 1:i + 3]:
            if " : " in ligne and not dates_fr(ligne) and len(ligne) < 120:
                return _separer(ligne)
            if _est_lieu(ligne):
                return _separer(ligne)
    # Enfin : une ligne qui ressemble à un nom de lieu, de préférence après la date
    i_date = next((i for i, l in enumerate(lignes) if dates_fr(l)), None)
    proches = lignes[i_date + 1:i_date + 8] if i_date is not None else []
    for ligne in proches + lignes:
        if _est_lieu(ligne):
            return _separer(ligne)
    return "", ""


def lire_fiche(url: str, categorie: str) -> Evenement | None:
    soup = page(url)
    ld = depuis_json_ld(json_ld_evenements(soup), url)
    if ld:
        e = ld[0]
        e.categorie = categorie
        return e
    titre = meta(soup, "og:title") or propre((soup.find("h1") or soup.find("title") or soup).get_text(" "))
    titre = titre_brut = re.sub(r"\s*[|–-]\s*Teskerti.*$", "", titre, flags=re.I)
    titre = re.sub(r"\s*[-–]\s*le\s+\d{1,2}/\d{1,2}(/\d{2,4})?\s*$", "", titre, flags=re.I)  # « Fuite - Le 02/11 »
    dates = sorted(set(dates_fr(soup.get_text(" "))))
    if not titre or not dates:
        return None
    lieu, adresse = lieu_de_la_fiche(soup, titre_brut)
    prix = re.search(r"(?:à partir de|a partir de)\s*(\d+(?:[.,]\d+)?)\s*(?:TND|DT)", soup.get_text(" "), re.I)
    prix = f"À partir de {prix.group(1)} DT" if prix else ""
    if re.search(r"\b(?:sold.?out|[ée]puis[ée]|guichet ferm[ée])\b", soup.get_text(" "), re.I):
        prix = f"{prix} · Complet" if prix else "Complet"
    return Evenement(titre=titre, debut=dates[0], fin=dates[-1] if len(dates) > 1 else None,
                     seances=dates, lien=url, lieu=lieu, adresse=adresse, categorie=categorie, prix=prix)


def recuperer(source: dict) -> list[Evenement]:
    opts = source.get("options") or {}
    exclues = {slug(c) for c in opts.get("categories_exclues", EXCLUES)}
    accueil = page(BASE)
    categories = [(u, t) for u, t in liens(accueil, "/category/") if u.rstrip("/").split("/")[-1] not in exclues]
    a_lire: dict[str, str] = {}
    for url_cat, _ in categories:
        nom = url_cat.rstrip("/").split("/")[-1]
        cat = next((v for k, v in CATEGORIES.items() if k in nom), source.get("categorie", "theatre"))
        for url_ev, _ in liens(page(url_cat), "/evenement/"):
            a_lire.setdefault(url_ev, cat)
        time.sleep(0.5)
    if not categories:  # si les catégories ne sont pas trouvées, on se contente de l'accueil
        a_lire = {u: source.get("categorie", "theatre") for u, _ in liens(accueil, "/evenement/")}
    if not a_lire:
        raise RuntimeError("aucun lien /evenement/ trouvé sur teskerti.tn (site modifié ?)")
    evenements = []
    for url, cat in a_lire.items():
        try:
            e = lire_fiche(url, cat)
            if e:
                evenements.append(e)
        except Exception:  # noqa: BLE001 — une fiche illisible n'arrête pas les autres
            continue
        time.sleep(0.5)
    return evenements
