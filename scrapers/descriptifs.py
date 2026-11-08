"""Petits descriptifs : événements, films, lieux, festivals, musées, artistes, organisateurs.

Tout est gratuit et sans clé obligatoire :
  événements  la page d'origine de l'annonce (lien « Source ») : description schema.org,
              balise og:description, ou premier paragraphe. Facebook, Instagram et PDF sont
              sautés (illisibles sans compte). Un texte commun à plusieurs pages d'un même site
              (« Achetez vos billets en ligne… ») est écarté.
  films       1. TMDb, si le secret TMDB_API_KEY existe (inscription gratuite sur themoviedb.org) :
                 vrai synopsis en français ;
              2. sinon Wikipédia (début de l'article), par l'élément Wikidata déjà trouvé ;
              3. sinon la notice d'une salle qui le projette.
              IMDb n'a pas d'API gratuite et interdit la copie de ses pages : on garde le lien.
  lieux, festivals, musées, organisateurs
              Wikipédia en français (ou anglais), par Wikidata, seulement pour un élément situé
              en Tunisie (organisateurs : le nom doit être exactement celui de l'élément) ;
              sinon la description du site officiel (OpenStreetMap pour un lieu, lien « Site web »
              d'un organisateur ; jamais Facebook ni Instagram).
  artistes    Wikipédia, par Wikidata : une personne dont le nom (au moins deux mots) est exactement
              celui de la fiche et qui a un article ; la personne tunisienne passe devant.
              En cas d'homonyme, corriger à la main (_data/descriptifs_manuels.yml).

Un texte écrit à la main dans _data/descriptifs_manuels.yml passe toujours devant.

Les réponses sont gardées dans _data/descriptifs.json : chaque page n'est lue qu'une fois,
une recherche sans résultat est refaite après 30 jours. Le site lit dans ce même fichier
les sections « lieux », « festivals », « musees », « artistes », « collectifs » ; le synopsis est ajouté à _data/films.json
et la notice d'un événement est écrite dans son fichier, comme celles des scrapers.

  python3 -m scrapers.descriptifs              tout
  python3 -m scrapers.descriptifs --sans-web   seulement ce qui est déjà en cache
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from .commun import RACINE, propre, resume, retours_ligne_casses, slug, telecharger
from .doublons import _lire
from .ecriture import DOSSIER_AUTO, _texte_brut
from .enrichir import _norm
from .wikidata import _valeurs

CACHE = RACINE / "_data" / "descriptifs.json"
MANUELS = RACINE / "_data" / "descriptifs_manuels.yml"
FILMS = RACINE / "_data" / "films.json"
LONGUEUR = 400            # une notice courte, coupée en fin de phrase
LONGUEUR_LIEU = 320
MAX_PAGES = 80            # pages nouvelles lues par passage (on reste discret avec les sites)
MAX_RECHERCHES = 120      # recherches Wikidata / TMDb nouvelles par passage (films d'abord, puis fiches)
REESSAI = dt.timedelta(days=30)
OUBLI = dt.timedelta(days=90)  # une page plus citée par aucun événement est oubliée

WIKIDATA = "https://www.wikidata.org/w/api.php"
UA = {"User-Agent": "agenda-nuit-tunis/1.0 (https://github.com/benjello/agenda-nuit-tunis)"}
TUNISIE = "Q948"
TMDB = "https://api.themoviedb.org/3"

_ILLISIBLES = re.compile(r"(?:^|\.)(?:facebook\.com|fb\.me|fb\.com|instagram\.com|x\.com|twitter\.com|tiktok\.com|"
                         r"youtube\.com|youtu\.be|linktr\.ee)$", re.I)
# Textes de remplissage, pas une description de l'événement.
_BANAL = re.compile(r"cookies?|javascript|tous droits r[ée]serv|all rights reserved|connectez-vous|log ?in|"
                    r"^\s*(?:achetez|r[ée]servez) vos (?:billets|places)|page introuvable|not found|404", re.I)


# ---------------------------------------------------------------- utilitaires

def _aujourd_hui() -> str:
    return dt.date.today().isoformat()


def _perime(entree: dict | None) -> bool:
    """À (re)chercher : jamais vu, ou cherché sans succès il y a plus de 30 jours."""
    if not entree:
        return True
    if entree.get("texte"):
        return False
    try:
        return dt.date.today() - dt.date.fromisoformat(entree.get("verifie", "")) > REESSAI
    except ValueError:
        return True


def _nettoyer(texte: str, n: int = LONGUEUR) -> str:
    t = BeautifulSoup(texte or "", "html.parser").get_text(" ") if "<" in (texte or "") else (texte or "")
    t = retours_ligne_casses(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\s*\n\s*", "\n", t).strip()
    t = re.sub(r"\n{2,}", "\n", t)
    return resume(t, n)


def lire_cache() -> dict:
    try:
        d = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        d = {}
    for k in ("pages", "recherches", "lieux", "festivals", "musees", "films", "artistes", "collectifs"):
        d.setdefault(k, {})
    return d


def ecrire_cache(cache: dict) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n")


def manuels() -> dict:
    try:
        d = yaml.safe_load(MANUELS.read_text()) or {}
    except (OSError, yaml.YAMLError):
        d = {}
    return {k: {str(c): str(v).strip() for c, v in (d.get(k) or {}).items() if v} for k in
            ("evenements", "films", "lieux", "festivals", "musees", "artistes", "collectifs")}


# ---------------------------------------------------------------- pages d'annonce

def _jsonld_descriptions(soup: BeautifulSoup) -> list[str]:
    res = []

    def parcourir(o):
        if isinstance(o, list):
            for x in o:
                parcourir(x)
        elif isinstance(o, dict):
            t = o.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(isinstance(x, str) and re.search(r"Event|Movie|CreativeWork|Product|TheaterEvent|Exhibition", x)
                   for x in types) and isinstance(o.get("description"), str):
                res.append(o["description"])
            for k in ("@graph", "itemListElement", "item", "subEvent", "workPresented"):
                if k in o:
                    parcourir(o[k])

    for s in soup.find_all("script", type="application/ld+json"):
        try:
            parcourir(json.loads(s.string or ""))
        except (ValueError, TypeError):
            continue
    return res


def _meta(soup: BeautifulSoup, *noms: str) -> str:
    for nom in noms:
        tag = soup.find("meta", attrs={"property": nom}) or soup.find("meta", attrs={"name": nom})
        if tag and tag.get("content"):
            return propre(tag["content"])
    return ""


def _paragraphes(soup: BeautifulSoup) -> str:
    """Les premiers vrais paragraphes du contenu principal."""
    for x in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        x.decompose()
    zone = (soup.find("article") or soup.find("main") or
            soup.find(class_=re.compile(r"entry-content|description|content|synopsis|resume", re.I)) or soup.body or soup)
    garde = []
    for p in zone.find_all("p"):
        t = propre(p.get_text(" "))
        if len(t) >= 60 and not _BANAL.search(t):
            garde.append(t)
        if sum(map(len, garde)) >= LONGUEUR:
            break
    return "\n".join(garde)


def extraire(html: str, titre: str = "") -> str:
    """Descriptif d'une page d'annonce, ou « » s'il n'y a rien d'utilisable."""
    soup = BeautifulSoup(html, "html.parser")
    candidats = [_nettoyer(d) for d in _jsonld_descriptions(soup)]
    candidats.append(_nettoyer(_meta(soup, "og:description", "twitter:description", "description")))
    meilleur = max((c for c in candidats if _utile(c, titre)), key=len, default="")
    # og:description est souvent tronquée (« … ») : le texte de la page est alors plus complet.
    if not meilleur or len(meilleur) < 120 or meilleur.endswith(("…", "...")):
        corps = _nettoyer(_paragraphes(soup))
        if _utile(corps, titre) and len(corps) > len(meilleur):
            meilleur = corps
    return meilleur


def _utile(texte: str, titre: str = "") -> bool:
    if len(texte) < 50 or _BANAL.search(texte[:200]):
        return False
    # Le titre seul, répété (« BAKMA - Cinéma Le Colisée ») : pas un descriptif.
    reste = re.sub(re.escape(titre), "", texte, flags=re.I) if titre else texte
    return len(re.sub(r"\W+", "", reste)) >= 40


def _lisible(lien: str) -> bool:
    if not lien or not lien.startswith("http"):
        return False
    u = urlparse(lien)
    return not _ILLISIBLES.search(u.netloc.split(":")[0]) and not u.path.lower().endswith((".pdf", ".jpg", ".png"))


def textes_generiques(pages: dict) -> set[str]:
    """Un même texte lu sur plusieurs pages d'un site est son slogan, pas une description."""
    vus = collections.Counter((urlparse(u).netloc, p.get("texte")) for u, p in pages.items() if p.get("texte"))
    return {t for (_, t), n in vus.items() if n >= 2}


# ---------------------------------------------------------------- Wikipédia, Wikidata, TMDb

def _wd(**params) -> dict:
    r = requests.get(WIKIDATA, params={"format": "json", **params}, headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def wikipedia(qid: str, n: int = LONGUEUR) -> dict | None:
    """Début de l'article Wikipédia (fr, sinon en) d'un élément Wikidata."""
    e = _wd(action="wbgetentities", ids=qid, props="sitelinks").get("entities", {}).get(qid, {})
    for langue in ("fr", "en"):
        titre = e.get("sitelinks", {}).get(f"{langue}wiki", {}).get("title")
        if not titre:
            continue
        url = f"https://{langue}.wikipedia.org/api/rest_v1/page/summary/{quote(titre.replace(' ', '_'), safe='')}"
        r = requests.get(url, headers=UA, timeout=30)
        if r.ok and r.json().get("extract") and r.json().get("type") != "disambiguation":
            d = r.json()
            return {"texte": _nettoyer(d["extract"], n), "source": "Wikipédia",
                    "url": d.get("content_urls", {}).get("desktop", {}).get("page", ""), "langue": langue}
    return None


def _noms(e: dict) -> set[str]:
    """Libellés et alias (toutes langues demandées) d'un élément, normalisés."""
    noms = {l["value"] for l in e.get("labels", {}).values()}
    for alias in e.get("aliases", {}).values():
        noms |= {a["value"] for a in alias}
    return {n for n in (_norm(x) for x in noms) if n}


def chercher_lieu(nom: str, strict: bool = False) -> str | None:
    """Élément Wikidata d'un lieu, musée, festival ou organisme situé en Tunisie, ou None.
    strict : le nom doit être celui de l'élément (ou un alias), pas seulement lui ressembler."""
    ids = []
    for langue in ("fr", "en"):
        for r in _wd(action="wbsearchentities", search=nom, language=langue, uselang="fr",
                     type="item", limit=5).get("search", []):
            if r["id"] not in ids:
                ids.append(r["id"])
    if not ids:
        return None
    entites = _wd(action="wbgetentities", ids="|".join(ids), props="claims|sitelinks|labels|aliases",
                  languages="fr|en|ar").get("entities", {})
    cible = _norm(nom)
    for qid in ids:  # dans l'ordre de pertinence de Wikidata
        e = entites.get(qid, {})
        if strict and cible not in _noms(e):
            continue
        pays = [c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                for c in e.get("claims", {}).get("P17", [])]
        if TUNISIE in pays and any(k in e.get("sitelinks", {}) for k in ("frwiki", "enwiki")):
            return qid
    return None


def chercher_personne(nom: str) -> str | None:
    """Élément Wikidata d'une personne dont le nom est exactement celui cherché et qui a un article
    Wikipédia ; à égalité, la personne tunisienne passe devant. Un seul mot (« Amin ») : trop de
    homonymes, on ne cherche pas."""
    if len(nom.split()) < 2:
        return None
    ids = []
    for langue in ("fr", "en"):
        for r in _wd(action="wbsearchentities", search=nom, language=langue, uselang="fr",
                     type="item", limit=7).get("search", []):
            if r["id"] not in ids:
                ids.append(r["id"])
    if not ids:
        return None
    entites = _wd(action="wbgetentities", ids="|".join(ids), props="claims|sitelinks|labels|aliases",
                  languages="fr|en|ar").get("entities", {})
    cible, candidats = _norm(nom), []
    for rang, qid in enumerate(ids):
        e = entites.get(qid, {})
        if "Q5" in _valeurs(e, "P31") and cible in _noms(e) and any(k in e.get("sitelinks", {}) for k in ("frwiki", "enwiki")):
            candidats.append((TUNISIE in _valeurs(e, "P27"), -rang, qid))
    return max(candidats)[2] if candidats else None


def tmdb(film: dict, cle: str) -> dict | None:
    """Synopsis TMDb en français : par l'identifiant IMDb s'il est connu, sinon par le titre."""
    params = {"api_key": cle, "language": "fr-FR"}
    resultats = []
    if film.get("imdb"):
        r = requests.get(f"{TMDB}/find/{film['imdb']}", params={**params, "external_source": "imdb_id"}, timeout=30)
        r.raise_for_status()
        resultats = r.json().get("movie_results", [])
    if not resultats:
        titre = re.split(r"\s+[-–/|]\s+", film["titre"])[0]
        r = requests.get(f"{TMDB}/search/movie", params={**params, "query": titre}, timeout=30)
        r.raise_for_status()
        annee_min = dt.date.today().year - 3  # films à l'affiche : récents (ou ressortie, on prend le risque)
        resultats = [x for x in r.json().get("results", []) if (x.get("release_date") or "9999")[:4] >= str(annee_min)]
    for x in resultats[:1]:
        if x.get("overview"):
            return {"texte": _nettoyer(x["overview"]), "source": "TMDb",
                    "url": f"https://www.themoviedb.org/movie/{x['id']}"}
    return None


# ---------------------------------------------------------------- les étapes

class Budget:
    def __init__(self, n: int, web: bool):
        self.n, self.web = n, web

    def prendre(self) -> bool:
        if not self.web or self.n <= 0:
            return False
        self.n -= 1
        return True


def _evenements(dossier: Path = DOSSIER_AUTO) -> list[tuple[Path, dict, str]]:
    res = []
    for f in sorted(dossier.glob("*/*.md")):
        champs, corps = _lire(f)
        if champs:
            res.append((f, champs, corps))
    return res


def lire_pages(evts, cache: dict, budget: Budget) -> None:
    """Lit la page d'origine des événements qui n'ont pas de notice."""
    # Un lien partagé par plusieurs titres (programme du mois, publication) ne décrit aucun d'eux.
    titres_par_lien = collections.defaultdict(set)
    for _, c, _ in evts:
        titres_par_lien[c.get("link", "")].add(c.get("title", ""))
    for _, c, corps in evts:
        lien = c.get("link", "")
        if corps.strip() or not _lisible(lien) or len(titres_par_lien[lien]) > 1:
            continue
        p = cache["pages"].get(lien)
        if p:
            p["vu"] = _aujourd_hui()
        if not _perime(p) or not budget.prendre():
            continue
        try:
            texte = extraire(telecharger(lien), c.get("title", ""))
            print(f"  page · {c.get('title')} : {len(texte)} caractères")
        except Exception as exc:  # noqa: BLE001 — une page en panne n'arrête rien
            print(f"  page · {c.get('title')} : {type(exc).__name__}: {exc}")
            texte = ""
        cache["pages"][lien] = {"texte": texte, "verifie": _aujourd_hui(), "vu": _aujourd_hui()}
        time.sleep(0.5)


def completer_films(cache: dict, budget: Budget, evts, mains: dict) -> list[dict]:
    """Ajoute « synopsis » (et sa source) à chaque film de _data/films.json."""
    try:
        films = json.loads(FILMS.read_text())
    except (OSError, ValueError):
        return []
    cle_tmdb = os.environ.get("TMDB_API_KEY", "").strip()
    notices_salles = {}  # lien d'une séance → notice écrite par la salle
    for _, c, corps in evts:
        if c.get("film") and corps.strip() and c.get("link"):
            notices_salles.setdefault(c["link"], corps.strip())
    for f in films:
        if f["id"] in mains["films"]:
            f.update(synopsis=_nettoyer(mains["films"][f["id"]]), synopsis_source="", synopsis_url="")
            continue
        entree = cache["films"].get(f["id"])
        if _perime(entree) and budget.prendre():
            trouve = None
            try:
                if cle_tmdb:
                    trouve = tmdb(f, cle_tmdb)
                if not trouve and f.get("wikidata"):
                    trouve = wikipedia(f["wikidata"])
            except Exception as exc:  # noqa: BLE001
                print(f"  film · {f['titre']} : {type(exc).__name__}: {exc}")
                continue
            entree = {**(trouve or {}), "verifie": _aujourd_hui()}
            cache["films"][f["id"]] = entree
            print(f"  film · {f['titre']} → {entree.get('source', 'rien')}")
        if entree:
            entree["vu"] = _aujourd_hui()
        if entree and entree.get("texte"):
            f.update(synopsis=entree["texte"], synopsis_source=entree.get("source", ""), synopsis_url=entree.get("url", ""))
        else:
            notice = next((notices_salles[s["lien"]] for s in f.get("salles", []) if s.get("lien") in notices_salles), "")
            if notice:
                f.update(synopsis=_nettoyer(notice), synopsis_source="", synopsis_url="")
    FILMS.write_text(json.dumps(films, ensure_ascii=False, indent=1) + "\n")
    return films


def ecrire_notices(evts, cache: dict, films: list[dict], mains: dict) -> int:
    """Écrit la notice trouvée dans chaque événement qui n'en a pas."""
    generiques = textes_generiques(cache["pages"])
    synopsis = {}
    for f in films:
        if f.get("synopsis"):
            for s in f.get("salles", []):
                synopsis[s.get("lien")] = (f["synopsis"], f.get("synopsis_source") or None)
    n = 0
    for fichier, c, corps in evts:
        if corps.strip():
            continue
        lien, source = c.get("link", ""), None
        texte = mains["evenements"].get(fichier.stem, "")
        if not texte:
            texte = (cache["pages"].get(lien) or {}).get("texte", "")
            if texte in generiques:
                texte = ""
        if not texte and c.get("film") and lien in synopsis:
            texte, source = synopsis[lien]
        if not texte:
            continue
        brut = fichier.read_text()
        entete = f"notice_source: {json.dumps(source, ensure_ascii=False)}\nauto: true\n---\n" if source else "auto: true\n---\n"
        if "\nauto: true\n---\n" not in brut:
            continue
        brut = brut.replace("\nauto: true\n---\n", "\n" + entete, 1).rstrip("\n") + "\n\n" + _texte_brut(texte) + "\n"
        fichier.write_text(brut)
        n += 1
    return n


def _fiches(dossier: str) -> dict[str, tuple[str, dict]]:
    """{nom de fichier sans .md : (titre, en-tête)} des fiches d'un dossier (_lieux, _artistes, _collectifs)."""
    res = {}
    for f in sorted((RACINE / dossier).glob("*.md")):
        c, _ = _lire(f)
        if c and c.get("title"):
            res[f.stem] = (str(c["title"]), c)
    return res


def _nom_court(titre: str) -> str:
    """« Beit al-Hikma (Académie…) », « La Boîte (Instagram) » → le nom seul."""
    return re.sub(r"\s*\([^)]*\)\s*", " ", titre).strip() or titre


def _accueil(url: str) -> str:
    """Page d'accueil du site d'une adresse de flux ou de page (…/feed/ → …/)."""
    u = urlparse(url)
    if re.search(r"feed|rss|atom|\.xml|\.ics|\.json|wp-json", u.path, re.I):
        return f"{u.scheme}://{u.netloc}/"
    return url


def _site_collectif(c: dict) -> str:
    """Site web (pas un réseau social) d'un organisateur, ou une chaîne vide."""
    for l in c.get("liens") or []:
        if l.get("reseau") == "site" and _lisible(l.get("url", "")):
            return l["url"]
    url = c.get("url_source") or ""
    return _accueil(url) if _lisible(url) else ""


def _site_lieu(stem: str) -> str:
    """Site du lieu trouvé par OpenStreetMap (scrapers/enrichir.py)."""
    try:
        osm = json.loads((RACINE / "_data" / "enrichi.json").read_text()).get("osm") or {}
    except (OSError, ValueError):
        return ""
    site = (osm.get(f"lieu:{stem}") or {}).get("website", "")
    return site if _lisible(site) else ""


def _lire_site(site: str, nom: str) -> dict | None:
    t = extraire(telecharger(site), nom)
    return {"texte": _nettoyer(t, LONGUEUR_LIEU), "source": "site officiel", "url": site} if t else None


def _trouver(groupe: str, el: dict) -> dict | None:
    """Wikipédia (par Wikidata), puis la description du site officiel."""
    if groupe == "artistes":
        qid = chercher_personne(el["nom"])
    else:
        qid = chercher_lieu(el["nom"], strict=groupe == "collectifs")
    trouve = wikipedia(qid, LONGUEUR_LIEU) if qid else None
    if not trouve and el.get("site"):
        trouve = _lire_site(el["site"], el["nom"])
    return trouve


def completer_lieux(cache: dict, budget: Budget, mains: dict) -> None:
    """Sections « lieux », « festivals », « musees », « artistes », « collectifs » lues par le site."""
    try:
        festivals = yaml.safe_load((RACINE / "_data" / "festivals.yml").read_text()) or []
    except OSError:
        festivals = []
    try:
        musees = yaml.safe_load((RACINE / "_data" / "musees.yml").read_text()) or []
    except OSError:
        musees = []
    groupes = {
        "lieux": {k: {"nom": _nom_court(t).split(",")[0], "site": _site_lieu(k)} for k, (t, _) in _fiches("_lieux").items()},
        "festivals": {f["id"]: {"nom": re.sub(r"\s*\([^)]*\)\s*$", "", f["nom"]), "site": f.get("site")}
                      for f in festivals if f.get("id")},
        "musees": {m["nom"]: {"nom": re.sub(r"\s*\([^)]*\)\s*$", "", m["nom"])} for m in musees if m.get("nom")},
        "artistes": {k: {"nom": t} for k, (t, _) in _fiches("_artistes").items()},
        "collectifs": {k: {"nom": _nom_court(t), "site": _site_collectif(c)} for k, (t, c) in _fiches("_collectifs").items()},
    }
    for groupe, elements in groupes.items():
        sortie = {}
        for cle, el in elements.items():
            if cle in mains[groupe]:
                sortie[cle] = {"texte": _nettoyer(mains[groupe][cle], LONGUEUR_LIEU)}
                continue
            r_cle = f"{groupe}:{slug(el['nom'])}"
            entree = cache["recherches"].get(r_cle)
            if _perime(entree) and budget.prendre():
                try:
                    trouve = _trouver(groupe, el)
                except Exception as exc:  # noqa: BLE001
                    print(f"  {groupe} · {el['nom']} : {type(exc).__name__}: {exc}")
                    continue
                entree = {**(trouve or {}), "verifie": _aujourd_hui()}
                cache["recherches"][r_cle] = entree
                print(f"  {groupe} · {el['nom']} → {entree.get('source', 'rien')}")
                time.sleep(0.3)
            if entree:
                entree["vu"] = _aujourd_hui()
            if entree and entree.get("texte"):
                sortie[cle] = {k: entree[k] for k in ("texte", "source", "url") if entree.get(k)}
        cache[groupe] = sortie


def oublier(cache: dict) -> None:
    limite = (dt.date.today() - OUBLI).isoformat()
    for k in ("pages", "recherches", "films"):
        cache[k] = {c: v for c, v in cache[k].items() if v.get("vu", v.get("verifie", "")) >= limite}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sans-web", action="store_true", help="n'utiliser que le cache")
    args = p.parse_args(argv)
    cache, mains = lire_cache(), manuels()
    evts = _evenements()
    lire_pages(evts, cache, Budget(MAX_PAGES, not args.sans_web))
    recherches = Budget(MAX_RECHERCHES, not args.sans_web)
    films = completer_films(cache, recherches, evts, mains)
    n = ecrire_notices(evts, cache, films, mains)
    completer_lieux(cache, recherches, mains)
    oublier(cache)
    ecrire_cache(cache)
    avec = sum(1 for f in films if f.get("synopsis"))
    print(f"Descriptifs : {n} notice(s) ajoutée(s) aux événements, {avec}/{len(films)} films avec synopsis, "
          f"{len(cache['lieux'])} lieux, {len(cache['festivals'])} festivals, {len(cache['musees'])} musées, "
          f"{len(cache['artistes'])} artistes, {len(cache['collectifs'])} organisateurs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
