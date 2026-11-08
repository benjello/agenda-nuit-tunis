"""Articles culturels de la presse (La Presse, Tunisie Numérique, Kapitalis, Webdo…), via RSS.

La presse annonce beaucoup d'événements que nous ne suivons pas directement (régions, maisons
de la culture, festivals). Un article devient un événement s'il :
  - parle d'un événement (festival, concert, spectacle, exposition…, voir MOTS) ;
  - donne une date à venir (« du 5 au 9 novembre », « le 12 novembre », « 12 novembre 2026 »).
Le lieu est cherché dans le texte (« à la Cité de la culture », « au Théâtre municipal »…).

Un article ne devient JAMAIS une entrée « Autre » : il faut une catégorie reconnue et un lieu. Un article sur
un festival ou une manifestation multi-jours (Jaou Tunis, Saisons de la création…) devient une entrée de festival
(champ « festival », catégorie de sa discipline, « spectacle » à défaut) même si le lieu est vague. Sinon l'article est gardé dans _data/presse.json et rattaché, à la fin du passage
(scrapers/doublons.py), à la manifestation officielle qu'il couvre (section « Dans la presse » de la fiche) ;
s'il n'y en a pas, il reste simplement dans ce fichier.

Options :
  garder   expression régulière qui remplace MOTS
  lieu     lieu par défaut quand le texte n'en donne pas (défaut : « Tunisie, voir l'article »)
"""
from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import re
import unicodedata
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup

from ..commun import Evenement, slug, categorie_du_titre, prix_du_texte, propre, resume, telecharger, toutes_dates
from ..commun import MOIS, RACINE
from ..lecteurs import _annee, jours_sans_annee, periode
from .rss import _racine

MOTS = (r"festival|concert|spectacle|exposition|vernissage|projection|pi[èe]ce|repr[ée]sentation|soir[ée]e|"
        r"rencontre|conf[ée]rence|journ[ée]es|r[ée]cital|one man show|stand.?up|salon du livre|foire|"
        r"carnaval|biennale|mus[ée]e|th[ée][âa]tre|op[ée]ra|danse|cin[ée]-?club|"
        # en arabe : festival, spectacle, concert, exposition, colloque, soirée, rencontre, pièce, journées
        r"مهرجان|عرض|حفل|معرض|ندوة|أمسية|سهرة|تظاهرة|ملتقى|مسرحية|أيام|لقاء|ورشة")
# Articles sur un événement à l'étranger (« Paris : la Saison Méditerranée… ») : écartés.
_ETRANGER = re.compile(r"\b(?:Paris|Marseille|Lyon|Cannes|Venise|Rome|Berlin|Londres|Madrid|Bruxelles|Gen[èe]ve|"
                       r"New York|Montr[ée]al|Le Caire|Duba[ïi]|Doha|Rabat|Casablanca|Marrakech|Alger|Oran|Beyrouth|Amman)\b")
_CONTENU = "{http://purl.org/rss/1.0/modules/content/}encoded"
_LIEU = re.compile(r"\b(?:à|au|aux|à la|à l['’])\s*((?:Cité|Théâtre|Maison|Palais|Espace|Centre|Musée|Galerie|"
                   r"Institut|Salle|Cinéma|Cinémathèque|Dar|Bir|Club|Opéra|Bibliothèque|Médiathèque|Complexe|"
                   r"Amphithéâtre|Fondation|Rotonde|Acropolium|Colisée|Ksar|Fort)\b[^,.;:()\n«»\"]{2,60})")


_GENERIQUE = re.compile(r"^(?:(?:theatre|cinema|salle|maison|espace|le|la|les|l|du|de|des|el)\s+)+")
_TROP_COURTS = {"tunis", "carthage", "la marsa", "marsa", "sousse", "sfax"}


def _plat(texte: str) -> str:
    """Texte sans accents ni ponctuation, « Quatrième » écrit « 4eme » comme dans le registre."""
    t = unicodedata.normalize("NFKD", str(texte).replace("’", "'")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\bquatrieme\b|\b4\s*e?me\b|\b4\s*eme\b", "4eme", t)
    return " " + re.sub(r"[^a-z0-9]+", " ", t).strip() + " "


_NOMS: list[tuple[str, str]] | None = None


def noms_de_lieux() -> list[tuple[str, str]]:
    """(forme cherchée dans un texte, nom du lieu dans le registre), du plus long au plus court.
    Le registre est _data/lieux.json (noms de lieux déjà vus dans l'agenda, avec leur fiche)."""
    global _NOMS
    if _NOMS is None:
        try:
            index = json.loads((RACINE / "_data" / "lieux.json").read_text()).get("index", {})
        except (OSError, ValueError):
            index = {}
        formes = {}
        for nom in index:
            if len(nom) > 60 or "http" in nom or any(ord(c) > 0x2000 for c in nom if not "\u0600" <= c <= "\u06ff"):
                continue
            base = _plat(nom.split(",")[0]).strip()
            for forme in {base, _GENERIQUE.sub("", base)}:
                if len(forme) >= 6 and forme not in _TROP_COURTS:
                    formes.setdefault(forme, nom)
        _NOMS = sorted(formes.items(), key=lambda kv: -len(kv[0]))
    return _NOMS


def lieu_connu(texte: str, noms: list[tuple[str, str]] | None = None) -> str:
    """Le premier lieu du registre cité dans le texte (« la salle du Quatrième Art, à Tunis » →
    « Théâtre Le 4ème Art »), ou "". Le lieu cité en premier gagne ; à égalité, le nom le plus long."""
    plat = _plat(texte)
    trouves = [(plat.find(f" {forme} "), -len(forme), nom) for forme, nom in (noms_de_lieux() if noms is None else noms)
               if f" {forme} " in plat]
    return min(trouves)[2] if trouves else ""


def _lire(xml: str):
    try:
        return _racine(xml)
    except ET.ParseError:
        # « & » nu dans un titre (Tunisie Numérique) : on l'échappe et on réessaie
        # caractères de contrôle invisibles (Tunisie Numérique) aussi
        xml = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml)
        return _racine(re.sub(r"&(?!\w+;|#\d+;|#x[0-9a-fA-F]+;)", "&amp;", xml))


class _Item:
    """Élément d'un flux trop abîmé pour l'analyse XML, lu balise par balise."""
    def __init__(self, bloc: str):
        self.bloc = bloc

    def findtext(self, nom: str, defaut: str = "") -> str:
        nom = {_CONTENU: "content:encoded"}.get(nom, nom)
        m = re.search(rf"<{nom}[^>]*>(.*?)</{nom}>", self.bloc, re.S)
        if not m:
            return defaut
        v = m.group(1).strip()
        return v[9:-3] if v.startswith("<![CDATA[") and v.endswith("]]>") else html.unescape(v)


def _items(xml: str):
    try:
        return list(_lire(xml).iter("item"))
    except ET.ParseError:
        return [_Item(b) for b in re.findall(r"<item>(.*?)</item>", xml, re.S)]


def _articles(xml: str) -> list[dict]:
    res = []
    for it in _items(xml):
        html = it.findtext(_CONTENU, "") or it.findtext("description", "")
        try:
            pub = email.utils.parsedate_to_datetime(it.findtext("pubDate", "")).date()
        except (TypeError, ValueError):
            pub = dt.date.today()
        res.append({"titre": propre(it.findtext("title", "")), "lien": propre(it.findtext("link", "")),
                    "texte": propre(BeautifulSoup(html, "html.parser").get_text(" ")), "date": pub})
    return res


_M = "|".join(sorted(MOIS, key=len, reverse=True))


def recoller(texte: str) -> str:
    """Remet les espaces perdus par le HTML : « jusqu'au27nov. » → « jusqu'au 27 nov. »,
    « du27 octobre au3 novembre » → « du 27 octobre au 3 novembre », « 27nov. » → « 27 nov. »."""
    texte = re.sub(r"\b(jusqu['’]?au|jusqu['’]?[àa]|du|au|le|depuis|partir du)(?=\d)", r"\1 ", texte, flags=re.I)
    texte = re.sub(rf"(?<=\d)(?=(?:{_M})\b)", " ", texte, flags=re.I)
    return texte


_RE_JUSQUAU = re.compile(rf"jusqu['’]?\s*(?:au|[àa])\s+(?:\w+\s+)?(\d{{1,2}}|1er)\s+({_M})\b\.?(?:\s+(\d{{4}}))?", re.I)
_RE_DU_AU = re.compile(rf"\bdu\s+(?:\w+\s+)?(\d{{1,2}}|1er)\s*({_M})?\b\.?\s*(?:\d{{4}}\s*)?"
                       rf"(?:au|[-–→])\s+(?:\w+\s+)?(\d{{1,2}}|1er)\s+({_M})\b\.?(?:\s+(\d{{4}}))?", re.I)


def _jour(j: str, m: str, a: str, ref: dt.date) -> dt.date | None:
    mois = MOIS[m.lower()]
    try:
        return dt.date(int(a) if a else _annee(mois, ref), mois, 1 if j.lower() == "1er" else int(j))
    except ValueError:
        return None


def periode_abregee(texte: str, ref: dt.date) -> tuple[dt.date | None, dt.date | None]:
    """« du 27 oct. au 27 nov. », « jusqu'au 27 novembre » (année facultative, mois abrégés)."""
    m = _RE_DU_AU.search(texte)
    if m:
        j1, m1, j2, m2, a = m.groups()
        fin = _jour(j2, m2, a, ref)
        debut = _jour(j1, m1 or m2, a, ref)
        if debut and fin:
            if debut > fin:
                debut = debut.replace(year=debut.year - 1)
            return debut, fin
    m = _RE_JUSQUAU.search(texte)
    if m:
        fin = _jour(*m.groups(), ref)
        if fin:
            return min(ref, fin), fin  # l'article est paru avant la fin : l'événement a déjà commencé
    return None, None


def _dates(texte: str, ref: dt.date) -> tuple[dt.date | None, dt.date | None]:
    """Première date à venir (ou période) citée dans le texte."""
    aujourd_hui = dt.date.today()
    limite = aujourd_hui + dt.timedelta(days=120)
    texte = recoller(texte)
    debut, fin = periode_abregee(texte, ref)
    if debut and fin and fin >= aujourd_hui and debut <= limite:
        return debut, fin
    p = periode(texte)
    if p:
        debut, fin = dt.date.fromisoformat(p[0]), dt.date.fromisoformat(p[-1])
        if fin >= aujourd_hui and debut <= limite:
            return debut, fin
    jours = {d.date() for d in toutes_dates(texte)}
    jours |= {dt.date.fromisoformat(j) for j in jours_sans_annee(texte, ref)}
    a_venir = sorted(j for j in jours if aujourd_hui <= j <= limite)
    return (a_venir[0], None) if a_venir else (None, None)


_RUBRIQUE = re.compile(r"^\s*(?:Tunisie|Culture|Cin[ée]ma|Th[ée][âa]tre|Musique|Expo(?:sition)?|Livres?|Agenda|Sortie|"
                       r"Critique|Festival|Danse|Arts?)\s*[:|–-]\s+", re.I)
_EVENEMENT = re.compile(r"festival|foire|salon|journ[ée]es|biennale|rencontres|semaine|mois|nuit|f[êe]te|"
                        r"\b20\d{2}\b|مهرجان|أيام|معرض", re.I)


_LIEU_TITRE = re.compile(r"^(?:à|au|aux|chez|dans|en)\s", re.I)
_CITE_TEXTE = re.compile(r"(?:exposition|spectacle|pi[èe]ce|film|concert|festival|[ée]v[ée]nement|rencontre|cycle|programme)"
                         r"[^«“\"]{0,40}[«“\"]\s*([^»”\"]{3,80}?)\s*[»”\"]", re.I)


def titre_evenement(titre: str, texte: str = "") -> str:
    """Le nom de l'événement dans un titre d'article :
    « Cinéma : Le Temps suspendu, un film hongrois à ne pas rater » → « Le Temps suspendu » ;
    « « Saveurs et amertume » à la Galerie TGM : Lorsque l'art… » → « Saveurs et amertume » ;
    « Foire nationale du livre tunisien: Traduire, transmettre… » → « Foire nationale du livre tunisien »."""
    t = _RUBRIQUE.sub("", titre, count=1).strip()
    avant, sep, apres = t.partition(":")
    if sep and _LIEU_TITRE.match(avant.strip()) and "«" not in avant:
        # « À l'Institut français de Tunis : La Syrie regardée… » : l'avant est un lieu, pas un nom ;
        # le vrai nom est cité dans le texte (« l'exposition « Images de Syrie… » »).
        m = _CITE_TEXTE.search(texte[:600])
        if m:
            return propre(m.group(1))
        t = apres.strip()
    m = re.search(r"[«“\"]\s*([^»”\"]{3,80}?)\s*[»”\"]", t)
    if m:
        return propre(m.group(1))
    avant, sep, apres = t.partition(":")
    if sep and 2 <= len(avant.split()) <= 8 and len(apres.split()) >= 3 and _EVENEMENT.search(avant):
        return propre(avant)
    t = re.split(r",\s+(?:un|une|le|la|les|des|ce|cette)\s", t, maxsplit=1)[0]
    return propre(t) or titre


# Un article sur un film (critique, sortie en salles) n'est pas un événement : ses séances viennent des
# cinémas (doublon sinon). On garde seulement un film montré lors d'un événement précis.
# L'article sert quand même : il est rattaché aux séances du film (articles_de_film, plus bas).
_FILM = re.compile(r"\bfilms?\b|cin[ée]ma|en salles?|[àa] l.affiche|\bsortie\b|long.m[ée]trage|documentaire|فيلم|سينما", re.I)
_SEANCE_UNIQUE = re.compile(r"festival|cin[ée].?club|projection|avant.premi[èe]re|journ[ée]es|r[ée]trospective|cycle|"
                            r"semaine du|nuit du|rencontre|d[ée]bat|مهرجان|نادي السينما|عرض خاص", re.I)


# Une nouvelle au passé (prix décerné, décès, bilan) n'annonce rien à venir : ni événement ni article à rattacher.
_NOUVELLE = re.compile(r"\b(?:distingue|distingu[ée]e?s?|r[ée]compense|remporte|d[ée]croche|rend hommage|d[ée]c[èe]s|"
                       r"nous a quitt[ée]s?|s['’]est (?:tenue?|d[ée]roul[ée]e?)|a eu lieu|ont (?:re[çc]u|remport[ée]))\b|"
                       r"\ba (?:[ée]t[ée] )?(?:distingu|re[çc]u|remport|obtenu|d[ée]cern|honor|sacr)", re.I)


def est_sortie_de_film(titre: str, texte: str = "") -> bool:
    return bool(_FILM.search(titre)) and not _SEANCE_UNIQUE.search(f"{titre} {texte[:300]}")


_FESTIVAL = re.compile(r"festival|biennale|\bsalon\b|foire|carnaval|journ[ée]es|\bsaisons?\b|rencontres|مهرجان|أيام", re.I)


def _est_festival(titre: str, nom: str) -> bool:
    return bool(_FESTIVAL.search(nom) or _FESTIVAL.search(titre))


def _categorie(a: dict, source: dict) -> str:
    """Catégorie lue dans le titre puis dans le début du texte ; vide si rien de net."""
    if re.search(r"\bgalerie\b|exposition|\bphoto|معرض", a["titre"], re.I):
        return "expo"
    c = categorie_du_titre(a["titre"]) or categorie_du_titre(a["texte"][:300])
    if c:
        return c
    if re.search(r"\bgalerie\b|exposition|\btoiles\b|vernissage", a["texte"][:300], re.I):
        return "expo"
    if re.search(r"\bth[ée][âa]tre\b|\bpi[èe]ce\b|مسرحية", a["texte"][:300], re.I):
        return "theatre"
    cat = source.get("categorie", "")
    return "" if cat in ("", "autre") else cat


def analyser(xml: str, source: dict) -> tuple[list[Evenement], list[dict]]:
    """(événements, articles seulement). Un article devient un événement s'il donne une date à venir,
    un lieu précis et une catégorie ; sinon il est rangé avec les articles à rattacher."""
    o = source.get("options") or {}
    mots = re.compile(o.get("garder", MOTS), re.I)
    journal = source.get("genre") == "presse"  # les délégations régionales (genre « administration ») gardent l'ancienne règle
    res, articles = [], []
    for a in _articles(xml):
        tout = f"{a['titre']}. {a['texte']}"
        if not a["titre"] or not mots.search(a["titre"] + " " + a["texte"][:400]):
            continue
        if _ETRANGER.search(a["titre"]):
            continue
        if est_sortie_de_film(a["titre"], a["texte"]):
            continue
        if _NOUVELLE.search(a["titre"]) or _NOUVELLE.search(a["texte"][:200]):
            continue
        debut, fin = _dates(tout, a["date"])
        if not debut:
            continue
        m = _LIEU.search(tout)
        lieu = (lieu_connu(tout[:1500]) or (propre(m.group(1)).rstrip(" .") if m else "")
                or o.get("lieu", "" if journal else "Tunisie, voir l'article"))
        categorie = _categorie(a, source) or ("" if journal else "autre")
        titre = titre_evenement(a["titre"], a["texte"])
        festival = journal and _est_festival(a["titre"], titre) and (fin is not None or _FESTIVAL.search(titre))
        if festival and not (lieu and categorie):  # manifestation sans lieu précis : entrée de festival
            lieu, categorie = lieu or "Tunisie, voir l'article", categorie or "spectacle"
        if lieu and categorie:
            res.append(Evenement(titre=titre, article=a["titre"], festival=slug(titre) if festival else "", debut=dt.datetime(debut.year, debut.month, debut.day),
                                 fin=dt.datetime(fin.year, fin.month, fin.day) if fin else None,
                                 lien=a["lien"] or source["url"], lieu=lieu, categorie=categorie,
                                 prix=prix_du_texte(tout), description=resume(a["texte"], 400)))
        elif a["lien"]:
            articles.append({"titre": a["titre"], "evenement": titre, "lien": a["lien"], "source": source.get("id", ""),
                             "source_nom": source.get("nom", ""), "date": a["date"].isoformat(),
                             "debut": debut.isoformat(), "fin": (fin or debut).isoformat(), "lieu": lieu})
    return res, articles


def depuis_flux(xml: str, source: dict) -> list[Evenement]:
    return analyser(xml, source)[0]


def articles_de_film(xml: str, source: dict) -> list[dict]:
    """Les articles sur un film (critique, sortie…), pour l'encadré « Ce qu'en dit la presse »
    des séances de ce film (voir scrapers/critiques.py)."""
    return [{"titre": a["titre"], "film": titre_evenement(a["titre"]), "lien": a["lien"],
             "source": source.get("id", ""), "source_nom": source.get("nom", ""), "date": a["date"].isoformat()}
            for a in _articles(xml) if a["titre"] and a["lien"] and _FILM.search(a["titre"])]


def recuperer(source: dict) -> list[Evenement]:
    xml = telecharger(source["url"])
    if not _items(xml):
        raise RuntimeError("flux vide ou illisible")
    if source.get("genre") == "presse":
        from .. import critiques
        critiques.garder(articles_de_film(xml, source))
    evenements, articles = analyser(xml, source)
    if source.get("genre") == "presse":
        critiques.garder(articles, critiques.FICHIER_EVENEMENTS)
    return evenements
