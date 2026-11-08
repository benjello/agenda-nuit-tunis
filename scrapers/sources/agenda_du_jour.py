"""Agenda du jour d'un journal : « Agenda du samedi 25 juillet 2026 : les principaux rendez-vous
en Tunisie » (Tunisie Numérique). Tout le pays, régions comprises.

Chaque article donne une journée, en blocs :
    ### 16h00 — Ben Guerdane
    **37e Festival international d'équitation de Ben Guerdane**
    📍 Hippodrome Marsa El Ksiba
    - Course nationale de chevaux arabes pur-sang
Un bloc = un événement. Le titre est le nom du festival (sinon la première ligne du
programme), le lieu est la ligne 📍 (sinon le nom en gras quand c'est un lieu), suivi de la ville.

On lit les articles par le flux RSS (options.flux), sinon par l'API WordPress du site
(recherche « principaux rendez-vous »).

Options :
  flux       adresse du flux RSS de la série (étiquette « agenda culturel »)
  recherche  recherches WordPress, séparées par « | » (défaut : RECHERCHES)
  titres     expression régulière des titres d'articles retenus (défaut : TITRES)
"""
from __future__ import annotations

import datetime as dt
import json
import re
from urllib.parse import quote_plus, urlsplit

from bs4 import BeautifulSoup

from ..commun import Evenement, categorie_du_titre, propre, telecharger, toutes_dates
from .presse import _articles

_BLOC = re.compile(r"^\s*(\d{1,2})\s*[hH:]\s*(\d{2})?\s*[—–-]+\s*(.{2,60})$")
_LIEU = re.compile(r"^(?:Maison|Musée|Théâtre|Centre|Espace|Palais|Dar|Cité|Salle|Hippodrome|Galerie|Complexe|"
                   r"Amphithéâtre|Bibliothèque|Médiathèque|Institut|Club|Fort|Ksar|Site|Place|Jardin|Parc|Cinéma|"
                   r"Stade|Plage|Port|Médina|Bir|Basilique|Mosquée|Zaouia|Rotonde)\b", re.I)


RECHERCHES = "agenda national|principaux rendez-vous|événements nationaux attendus|programmés ce soir"
# « Agenda du samedi 25 juillet… », « Tunisie : les événements nationaux attendus ce vendredi 10 juillet »,
# « Festivals d'été : le calendrier des spectacles programmés ce soir »
TITRES = r"agenda|rendez-vous|[ée]v[ée]nements nationaux|programm[ée]s ce soir"


# L'agenda du jour mêle culture, économie et politique : on ne garde que les blocs culturels.
CULTURE = re.compile(r"festival|concert|spectacle|exposition|vernissage|projection|th[ée][âa]tre|pi[èe]ce|danse|"
                     r"cin[ée]ma|\bfilms?\b|musique|musical|r[ée]cital|soir[ée]e|chant|po[ée]sie|lecture|livre|"
                     r"mus[ée]e|patrimoine|\bart\b|\barts\b|artiste|culturel|culture|carnaval|op[ée]ra|orchestre|"
                     r"humour|stand.?up|one.?man|conte|marionnette|photo|galerie|biennale|"
                     r"مهرجان|عرض|حفل|معرض|مسرح|سينما|موسيق|ثقاف|فن", re.I)
PAS_CULTURE = re.compile(r"parlement|\bARP\b|assembl[ée]e|budget|ministre|minist[èe]re|conseil|commission|"
                         r"pl[ée]ni[èe]re|bourse|\bBCT\b|entreprise|investissement|agricult|exportation|"
                         r"syndicat|\bUGTT\b|tribunal|proc[èe]s|[ée]lection", re.I)


def _lignes(contenu: str) -> list[str]:
    soupe = BeautifulSoup(contenu, "html.parser")
    for br in soupe.find_all("br"):
        br.replace_with("\n")
    res = []
    for el in soupe.find_all(["h2", "h3", "h4", "p", "li"]):
        if el.find(["p", "li"]):  # un conteneur : ses enfants seront lus
            continue
        gras = el.name == "p" and el.find(["strong", "b"]) and propre(el.find(["strong", "b"]).get_text()) == propre(el.get_text())
        for l in el.get_text().split("\n"):
            l = propre(l)
            if l:
                res.append(("li" if el.name == "li" else "gras" if gras else el.name, l))
    return res


def blocs(contenu: str) -> list[dict]:
    res, bloc = [], None
    for balise, l in _lignes(contenu):
        m = _BLOC.match(l)
        if m and (balise in ("h2", "h3", "h4", "gras") or len(l) < 50):
            bloc = {"heure": (int(m.group(1)), int(m.group(2) or 0)), "ville": m.group(3).strip(" .:"),
                    "nom": "", "lieu": "", "programme": []}
            res.append(bloc)
            continue
        if bloc is None:
            continue
        if l.startswith("📍"):
            bloc["lieu"] = propre(l.lstrip("📍 :"))
        elif not bloc["nom"] and balise != "li":
            bloc["nom"] = l
        else:
            bloc["programme"].append(l.lstrip("•-– "))
    return res


def evenements(article: dict, contenu: str) -> list[Evenement]:
    jours = [d.date() for d in toutes_dates(article["titre"])]
    if not jours and re.search(r"ce soir|aujourd.hui", article["titre"], re.I) and article.get("date"):
        jours = [article["date"]]  # « programmés ce soir » : le jour de publication
    if not jours:
        return []
    jour = jours[0]
    res = []
    for b in blocs(contenu):
        nom, prog = b["nom"], b["programme"]
        tout = " ".join([nom, b["lieu"]] + prog)
        if not CULTURE.search(tout) or (PAS_CULTURE.search(tout) and not re.search(r"festival|مهرجان", tout, re.I)):
            continue
        lieu = b["lieu"] or (nom if _LIEU.match(nom) else "")
        festival = "" if lieu == nom else nom
        titre = festival or (prog[0] if prog else lieu)
        if not titre:
            continue
        lieu = lieu or b["ville"]
        if b["ville"].split(" (")[0].lower() not in lieu.lower():
            lieu = f"{lieu}, {b['ville']}"
        texte = "\n".join(x for x in [festival] + prog if x)
        h, mn = b["heure"]
        try:
            debut = dt.datetime(jour.year, jour.month, jour.day, h, mn)
        except ValueError:
            debut = dt.datetime(jour.year, jour.month, jour.day)
        res.append(Evenement(titre=titre[:120], debut=debut, lien=article["lien"], lieu=lieu[:90],
                             categorie=categorie_du_titre(f"{titre} {festival}") or "autre", description=texte))
    return res


def _par_api(source: dict) -> list[tuple[dict, str]]:
    o = source.get("options") or {}
    base = "{0.scheme}://{0.netloc}".format(urlsplit(source["url"]))
    res, vus = [], set()
    for mots in o.get("recherche", RECHERCHES).split("|"):
        url = f"{base}/wp-json/wp/v2/posts?search={quote_plus(mots.strip())}&orderby=date&order=desc&per_page=10&_fields=title,link,date,content"
        for p in json.loads(telecharger(url)):
            if p.get("link") in vus:
                continue
            vus.add(p.get("link"))
            titre = propre(BeautifulSoup((p.get("title") or {}).get("rendered", ""), "html.parser").get_text())
            try:
                jour = dt.date.fromisoformat(str(p.get("date"))[:10])
            except ValueError:
                jour = None
            res.append(({"titre": titre, "lien": p.get("link", ""), "date": jour}, (p.get("content") or {}).get("rendered", "")))
    return res


def _par_flux(source: dict) -> list[tuple[dict, str]]:
    o = source.get("options") or {}
    if not o.get("flux"):
        return []
    xml = telecharger(o["flux"])
    res = []
    for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
        bloc = m.group(1)
        c = re.search(r"<content:encoded>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</content:encoded>", bloc, re.S)
        a = _articles(f"<rss><channel><item>{bloc}</item></channel></rss>")
        if a and c:
            res.append((a[0], c.group(1)))
    return res


def recuperer(source: dict) -> list[Evenement]:
    o = source.get("options") or {}
    garder = re.compile(o.get("titres", TITRES), re.I)
    # Les deux chemins : le flux ne donne que les derniers articles de l'étiquette,
    # l'API retrouve les autres séries (« événements nationaux attendus… »).
    articles, erreurs, vus = [], [], set()
    for lire in (_par_flux, _par_api):
        try:
            for a, contenu in lire(source):
                if garder.search(a["titre"]) and a["lien"] not in vus:
                    vus.add(a["lien"])
                    articles.append((a, contenu))
        except Exception as exc:  # noqa: BLE001 — on essaie l'autre chemin
            erreurs.append(f"{lire.__name__}: {exc}"[:150])
    if not articles:
        raise RuntimeError("aucun article d'agenda lisible" + (f" ({'; '.join(erreurs)})" if erreurs else ""))
    print(f"  {source['id']} : {len(articles)} article(s) d'agenda, " + ", ".join(a["titre"][:50] for a, _ in articles[:4])
          + (f" ; {'; '.join(erreurs)}" if erreurs else ""))
    aujourd_hui = dt.date.today()
    res = []
    for a, contenu in articles:
        res += [e for e in evenements(a, contenu) if e.debut.date() >= aujourd_hui]
    return res
