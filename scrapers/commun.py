"""Outils partagés par tous les scrapers : téléchargement, dates, format commun."""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup

RACINE = Path(__file__).resolve().parent.parent
DEBUG_DIR: Path | None = None  # rempli par --debug

# En-têtes d'un navigateur ordinaire : certains sites refusent les robots trop visibles.
ENTETES = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
}
_session = requests.Session()
_session.headers.update(ENTETES)


class EnAttente(Exception):
    """La source n'a pas pu être lue, mais ce n'est pas une panne du site
    (clé d'accès pas encore configurée…). Les événements déjà récupérés sont gardés."""


def telecharger(url: str) -> str:
    # Un délai dépassé ou une coupure passagère n'est pas une panne du site : on réessaie
    # (2 s, 5 s) avant d'abandonner. Les erreurs HTTP (404, 403…) ne sont pas réessayées.
    for attente in (2, 5, None):
        try:
            r = _session.get(url, timeout=30)
            break
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attente is None:
                raise
            time.sleep(attente)
    r.raise_for_status()
    r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else "utf-8"
    if DEBUG_DIR:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / (slug(url)[:120] + ".html")).write_text(r.text)
    return r.text


def telecharger_json(url: str):
    return json.loads(telecharger(url))


def page(url: str) -> BeautifulSoup:
    return BeautifulSoup(telecharger(url), "html.parser")


def slug(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "evenement"


def propre(texte: str | None) -> str:
    return re.sub(r"\s+", " ", texte or "").strip()


# « rn » à la place des retours à la ligne : la billetterie d'El Teatro sépare les noms par « \r\n »,
# l'échappement se perd et il reste « rn » collé au mot suivant (« Baraketirn Mohamed »).
# On ne remplace que « rn » entre une lettre (ou une fin de phrase) et une majuscule ou une lettre arabe,
# pour ne pas toucher aux mots ordinaires (« journée », « Marne »…).
_RN_CASSE = re.compile(r"(?<=[^\W\d_]|[.…!?»)])rn(?=[A-ZÀ-ÖØ-Þ؀-ۿ])")


def retours_ligne_casses(texte: str | None) -> str:
    """Remet les retours à la ligne là où une source a laissé « rn » à la place."""
    return _RN_CASSE.sub("\n", texte or "")


MOIS = {
    "janvier": 1, "janv": 1, "fevrier": 2, "février": 2, "fevr": 2, "févr": 2, "mars": 3,
    "avril": 4, "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "août": 8,
    "septembre": 9, "sept": 9, "octobre": 10, "oct": 10, "novembre": 11, "nov": 11,
    "decembre": 12, "décembre": 12, "dec": 12, "déc": 12,
    # mois en arabe : noms maghrébins (جانفي…) et orientaux (يناير…)
    "جانفي": 1, "يناير": 1, "فيفري": 2, "فبراير": 2, "مارس": 3, "أفريل": 4, "أبريل": 4, "افريل": 4,
    "ماي": 5, "مايو": 5, "جوان": 6, "يونيو": 6, "جويلية": 7, "يوليو": 7, "أوت": 8, "اوت": 8,
    "أغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}
_RE_DATE = re.compile(
    r"(\d{1,2})(?:er)?\s+(" + "|".join(sorted(MOIS, key=len, reverse=True)) + r")\.?\s+(\d{4})"
    r"(?:\s*(?:,|à|a|-|–|\()?\s*(\d{1,2})\s*[:hH]\s*(\d{2})?)?",
    re.IGNORECASE,
)


def dates_fr(texte: str) -> list[dt.datetime]:
    """Toutes les dates françaises d'un texte : « 07 Novembre 2026 à 19:30 », « 5 nov. 2026 »…"""
    res = []
    for j, m, a, h, mn in _RE_DATE.findall(texte):
        try:
            res.append(dt.datetime(int(a), MOIS[m.lower()], int(j), int(h or 0), int(mn or 0)))
        except ValueError:
            continue
    return res


_RE_NUM = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b(?:\D{0,12}?(\d{1,2})\s*[:hH]\s*(\d{2})?)?")


def dates_num(texte: str) -> list[dt.datetime]:
    """Dates écrites en chiffres : « 26.09.2026 », « 26/09/2026 à 19h00 »."""
    res = []
    for j, m, a, h, mn in _RE_NUM.findall(texte):
        try:
            res.append(dt.datetime(int(a), int(m), int(j), int(h or 0), int(mn or 0)))
        except ValueError:
            continue
    return res


def toutes_dates(texte: str) -> list[dt.datetime]:
    return sorted(set(dates_fr(texte) + dates_num(texte)))


_RE_PLAGE_HEURES = re.compile(
    r"(?<![\d/.])(?:de\s+|from\s+|[àa]\s+partir\s+de\s+)?([01]?\d|2[0-3])\s*[hH:]\s*([0-5]\d)?\s*"
    r"(?:à|a|-|–|—|to|till|until|jusqu.[àa])\s*([01]?\d|2[0-3]|24)\s*[hH:]\s*([0-5]\d)?(?!\d)", re.I)
_RE_HEURE_CUE = re.compile(
    r"(?:\b(?:[àa]|dès|des|vers|at|from|@|starts?(?:\s+at)?|d[ée]but|ouverture(?:\s+des\s+portes)?|doors?|"
    r"horaires?|heure|rdv|rendez-vous)\b\s*:?\s*|[🕒🕗🕖🕘🕕🕔⏰🕐🕑🕓🕙🕚🕛🕜🕝🕞🕟]\s*)"
    r"([01]?\d|2[0-3])\s*[hH:]\s*([0-5]\d)?(?!\d)", re.I)
_RE_HEURE_AMPM = re.compile(r"(?<![\d:])(1[0-2]|0?[1-9])(?:[:h]([0-5]\d))?\s*([ap])\.?m\b", re.I)


def horaire_du_texte(texte: str) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Heure de début (et de fin si le texte la donne) lue dans une annonce.

    « de 19h à 21h30 », « 20:00 – 23:00 », « à 20h30 », « doors 9pm ».
    Renvoie (None, None) s'il n'y a pas d'heure ou si le texte en donne plusieurs
    qui diffèrent (séances multiples) : mieux vaut aucune heure qu'une heure fausse.
    """
    texte = texte or ""
    plages = {(int(a), int(b or 0), int(c) % 24, int(d or 0)) for a, b, c, d in _RE_PLAGE_HEURES.findall(texte)}
    plages = {p for p in plages if (p[0], p[1]) != (p[2], p[3])}
    if len(plages) == 1:
        a, b, c, d = plages.pop()
        return (a, b), (c, d)
    if plages:
        return None, None
    debuts = {(int(h), int(m or 0)) for h, m in _RE_HEURE_CUE.findall(texte)}
    for h, m, ap in _RE_HEURE_AMPM.findall(texte):
        h = int(h) % 12 + (12 if ap.lower() == "p" else 0)
        debuts.add((h, int(m or 0)))
    toutes = {(int(h), int(m or 0)) for h, m in re.findall(r"(?<![\d:.,/])([01]?\d|2[0-3])\s*[hH:]\s*([0-5]\d)?(?!\d)", texte)}
    if len(debuts) == 1 and toutes <= debuts:  # une autre heure sans mot-clé : texte ambigu
        return debuts.pop(), None
    return None, None


def json_ld_evenements(soup: BeautifulSoup) -> list[dict]:
    """Événements schema.org (JSON-LD) présents dans une page, s'il y en a."""
    trouves = []

    def parcourir(obj):
        if isinstance(obj, list):
            for o in obj:
                parcourir(o)
        elif isinstance(obj, dict):
            t = obj.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(isinstance(x, str) and x.endswith("Event") for x in types):
                trouves.append(obj)
            for k in ("@graph", "itemListElement", "item", "subEvent"):
                if k in obj:
                    parcourir(obj[k])

    for s in soup.find_all("script", type="application/ld+json"):
        try:
            parcourir(json.loads(s.string or ""))
        except (json.JSONDecodeError, TypeError):
            continue
    return trouves


def meta(soup: BeautifulSoup, nom: str) -> str:
    tag = soup.find("meta", attrs={"property": nom}) or soup.find("meta", attrs={"name": nom})
    return propre(tag.get("content")) if tag and tag.get("content") else ""


@dataclass
class Evenement:
    """Format commun : ce que chaque scraper doit produire pour un événement."""
    titre: str
    debut: dt.datetime
    lien: str                      # page d'origine (fiche du lieu, billetterie…)
    lieu: str = ""
    fin: dt.datetime | None = None
    adresse: str = ""
    categorie: str = ""
    prix: str = ""
    seances: list[dt.datetime] = field(default_factory=list)
    image: str = ""                # affiche, si la source en donne une
    film: bool = False             # film à l'affiche (séances = jours de projection)
    imdb: str = ""                 # identifiant IMDb (tt…), si connu
    duree: int | None = None       # minutes
    genres: list[str] = field(default_factory=list)
    description: str = ""          # notice : quelques lignes tirées de la source (légende, résumé)
    artistes: list[str] = field(default_factory=list)  # line-up, si la source le donne
    festival: str = ""             # presse : identifiant d'un festival ou d'une manifestation repérée dans un article
    article: str = ""              # presse : titre de l'article (le titre ci-dessus est le nom de l'événement)


@dataclass
class Publication:
    """Une publication Facebook avec image (programme, affiche) et le texte lu dessus."""
    lien: str
    date: str                                         # AAAA-MM-JJ
    texte: str = ""                                   # texte de la publication
    images: list[str] = field(default_factory=list)   # chemins dans le site (assets/…)
    ocr_facebook: str = ""                            # texte de l'image lu par Facebook
    ocr: str = ""                                     # texte de l'image lu par Tesseract

    def en_dict(self):
        return asdict(self)


def film(titre: str, lien: str, lieu: str, jours, adresse: str = "", **autres) -> Evenement | None:
    """Un film à l'affiche dans une salle, au même format que tout événement :
    catégorie cinéma, une séance par jour (« AAAA-MM-JJ ») ou par horaire (« AAAA-MM-JJ HH:MM »)."""
    seances = sorted({dt.datetime.fromisoformat(j[:16]) for j in jours})
    if not seances:
        return None
    return Evenement(titre=titre, debut=seances[0], fin=seances[-1], lien=lien, lieu=lieu, adresse=adresse,
                     categorie="cinema", seances=seances, film=True, **autres)


# Mots du titre qui disent la vraie catégorie, quand la rubrique de la source est trop large
# (tunis.events range clubs et concerts ensemble). Le premier qui correspond gagne.
_CATEGORIES_DU_TITRE = [
    ("karaoke", r"\bkara[ou]k[ée]\b"),
    ("humour", r"stand[- ]?up|\bcomedy\b|\bhumou?r\b|one[- ]man[- ]show|\bcom[ée]die club\b|open mic"),
    ("cabaret", r"\bcabaret\b|d[îi]ner[- ]spectacle|\brevue\b|\bburlesque\b|soir[ée]e orientale|\bbelly ?dance\b|danse orientale"),
    ("festival", r"\bfestival\b|\bopen[- ]air\b|day ?party|\bfest\b|\bboat party\b|pool ?party|beach party"),
    ("club", r"\bdj\b|\bdjs\b|\btechno\b|\bhouse\b|\bafro ?house\b|\bclub(?:bing)?\b|\brave\b|\bb2b\b|\ball night long\b"
             r"|\bdisco\b|\bamapiano\b|\bdrum ?(?:&|and|n) ?bass\b|\bsound ?system\b|\bsecret vibes\b"),
    ("bar", r"\bafterwork\b|after[- ]work|\brooftop\b|\blounge\b|\bhappy hour\b|\bpub\b|\bsunset\b"),
    ("discotheque", r"\bdiscoth[èe]que\b|\bnight ?club\b|\bbo[îi]te de nuit\b|ann[ée]es? (?:80|90|2000)|\bladies night\b|soir[ée]e [àa] th[èe]me"),
    ("concert", r"\bconcert\b|\blive\b|\bjazz\b|\brap\b|\bmalouf\b|\bmezoued\b|\bmizwed\b|\brock\b|\bblues\b|\bgnawa\b|\bstambali\b"),
]

# Ce qui n'est pas une sortie de nuit : écarté même si la rubrique de la source est « soirées ».
_PAS_LA_NUIT = re.compile(
    r"movie night|cin[ée][- ]?club|\bprojection\b|\bvernissage\b|\bexposition\b|\bconf[ée]rence\b|table ronde"
    r"|\bateliers?\b|\bworkshops?\b|\bmasterclass\b|\bformations?\b|\bsalon\b|\bcybercamp\b|\bhackathon\b|\bcoaching\b"
    r"|\bd[ée]dicace\b|\bmarionnettes?\b|\bvisite guid[ée]e\b|\bmus[ée]e\b", re.I)

# Catégories de l'agenda culturel encore produites par certains scrapers, ramenées à celles de la nuit.
ANCIENNES_CATEGORIES = {"musique": "concert", "clubbing": "club", "danse": "club", "spectacle": "cabaret",
                        "nightlife": "club"}


def categorie_du_titre(titre: str) -> str:
    """Catégorie déduite du titre, ou "" si rien de net."""
    for cat, motif in _CATEGORIES_DU_TITRE:
        if re.search(motif, titre, re.I):
            return cat
    return ""


def pas_la_nuit(titre: str) -> bool:
    """Vrai pour une annonce culturelle de jour (film, expo, conférence, atelier) : pas pour cet agenda."""
    return bool(_PAS_LA_NUIT.search(titre or ""))


_CATEGORIES_NUIT: set[str] | None = None


def categorie_nuit(categorie: str, titre: str = "") -> str:
    """Catégorie de l'agenda de la nuit pour un événement, ou "" s'il n'en est pas.
    Le titre l'emporte (« DJ set » → club) ; sinon la catégorie de la source, traduite si besoin."""
    global _CATEGORIES_NUIT
    if _CATEGORIES_NUIT is None:
        import yaml
        _CATEGORIES_NUIT = set(yaml.safe_load((RACINE / "_data" / "categories.yml").read_text()) or {})
    if pas_la_nuit(titre):
        return ""
    cat = categorie_du_titre(titre) or ANCIENNES_CATEGORIES.get(categorie, categorie)
    return cat if cat in _CATEGORIES_NUIT else ""


_RE_LIEU = re.compile(r"\bLieu\s*:\s*([^\n]{3,150})", re.I)
_RE_PLAGE = re.compile(r"\b(\d{1,2})(?:er)?\s*(?:[–-]|au)\s*(\d{1,2})(?:er)?\s+([A-Za-zéèûôÉ.]+)\s+(\d{4})")


def details_page(texte: str) -> dict:
    """Ce que la page d'un événement dit mieux que le flux : « Lieu : … », « Dates : 3–5 décembre 2026 »."""
    res = {}
    m = _RE_LIEU.search(texte)
    if m:
        lieu = re.split(r"\s*(?:📅|🕒|⏰|Dates?\s*:|Horaires?\s*:|Heure\s*:)", m.group(1))[0]
        res["lieu"] = propre(lieu).strip(" .,;")
    m = _RE_PLAGE.search(texte)
    if m and m.group(3).lower() in MOIS:
        try:
            mois, an = MOIS[m.group(3).lower()], int(m.group(4))
            res["debut"] = dt.datetime(an, mois, int(m.group(1)))
            res["fin"] = dt.datetime(an, mois, int(m.group(2)))
        except ValueError:
            pass
    return res


# Cours et activités payantes récurrentes (yoga, fitness…) : gardés mais placés en bas de liste,
# pour que l'agenda mette en avant la création (concerts, pièces, expos).
_COMMERCIAL = re.compile(r"\byoga\b|pilates|fitness|zumba|m[ée]ditation|sophrologie|bien[- ][êe]tre|\bbrunch\b|"
                         r"happy hour|team ?building|cours (?:de|d')|\bcoaching\b|d[ée]veloppement personnel", re.I)


def est_discret(titre: str) -> bool:
    return bool(_COMMERCIAL.search(titre))


_FAMILLE = re.compile(r"jeune public|\benfants?\b|en famille|\bfamilial|\bkids?\b|\bjunior|marionnette|\bcontes?\b|"
                      r"atelier (?:pour )?(?:les )?(?:petits|enfants)|d[èe]s \d{1,2} ans|\bpetits\b|"
                      r"cin[ée].?go[ûu]ter|heure du conte|atelier cr[ée]atif|[ée]veil musical|\bjeunesse\b|"
                      r"vacances scolaires|\bclowns?\b|\bfamily\b|children|"
                      r"أطفال|للأطفال|الطفل|الأطفال|عرائس|العائلة|الصغار", re.I)
# Dans une notice, « enfants » seul ne suffit pas (« le mariage de leurs enfants ») : il faut une tournure claire.
_FAMILLE_NOTICE = re.compile(r"jeune public|en famille|pour (?:les )?(?:petits|enfants)|d[èe]s \d{1,2} ans|[àa] partir de \d{1,2} ans|"
                             r"cin[ée].?go[ûu]ter|heure du conte|ateliers? (?:pour |des )?enfants|spectacle (?:pour )?enfants|marionnette|"
                             r"\bkids?\b|children|family|للأطفال|مسرح الطفل|عرائس", re.I)
_AGE_MIN = re.compile(r"(?:d[èe]s|[àa] partir de|from|ages?|من)\s*(\d{1,2})\s*(?:ans|years|yrs|سنوات|سنة)", re.I)
_AGE_PLAGE = re.compile(r"\b(\d{1,2})\s*(?:-|–|à|a|to|إلى)\s*(\d{1,2})\s*(?:ans|years|سنوات|سنة)", re.I)


def age_conseille(*textes: str) -> str | None:
    """« 4 » (dès 4 ans) ou « 3-6 » (de 3 à 6 ans), lu dans l'annonce."""
    for t in textes:
        m = _AGE_PLAGE.search(t or "")
        if m and int(m.group(1)) < int(m.group(2)) <= 18:
            return f"{int(m.group(1))}-{int(m.group(2))}"
        m = _AGE_MIN.search(t or "")
        if m and 1 <= int(m.group(1)) <= 16:
            return str(int(m.group(1)))
    return None


def est_famille(*textes: str) -> bool:
    """Spectacle, atelier ou film pour les enfants ou à voir en famille."""
    titre, *notices = textes or [""]
    return bool(_FAMILLE.search(titre or "")) or any(_FAMILLE_NOTICE.search(t or "") for t in notices)


def resume(texte: str, n: int = 500) -> str:
    """Notice courte : texte propre, coupé à la fin d'une phrase ou d'un mot."""
    t = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", (texte or "").strip()))
    if len(t) <= n:
        return t
    coupe = t[:n]
    fin = max(coupe.rfind(". "), coupe.rfind("\n"))
    return (coupe[:fin + 1] if fin > n * 0.5 else coupe.rsplit(" ", 1)[0] + " …").strip()


_GRATUIT = re.compile(r"entr[ée]e (?:libre|gratuite)|acc[eè]s (?:libre|gratuit)|\bgratuit|free entry|\bfree\b|"
                      r"الدخول مجاني|دخول مجاني|مجانا", re.I)
_MONTANT = re.compile(r"(?<![\d.,])(\d{1,4}(?:[.,]\d{1,3})?)\s*(?:DT|TND|dinars?|د\.?ت)\b", re.I)


def prix_du_texte(texte: str) -> str:
    """« Gratuit », « 20 DT » ou « 10 à 30 DT » d'après une légende ou un article, sinon ""."""
    if _GRATUIT.search(texte or ""):
        return "Gratuit"
    montants = sorted({float(m.replace(",", ".")) for m in _MONTANT.findall(texte or "")} - {0.0})
    montants = [m for m in montants if m < 1000]  # « 1500 DT » : sans doute un prix ou une bourse, pas un billet
    if not montants:
        return ""
    f = lambda x: f"{x:g}"  # noqa: E731
    return f"{f(montants[0])} DT" if len(montants) == 1 else f"{f(montants[0])} à {f(montants[-1])} DT"


# --- Granularité : un événement précis (un film, une expo), pas une rubrique ni une annonce de service ---

# Préfixes de cycle ou de rubrique devant le titre d'un film : « Movie Night: UN FILS », « Mercredis-Ciné Level Five ».
_PREFIXE_FILM = re.compile(r"^\s*(?:(?:movie night|mercredis?[- ]?cin[ée]|cin[ée][- ]?club|cin[ée][- ]?go[ûu]ter|avant[- ]premi[èe]re|"
                           r"soir[ée]e cin[ée]ma)\s*(?::|-|–|\|)?|(?:projection(?: du film)?|cin[ée]ma|film)\s*(?::|–|\|| - ))"
                           r"\s*(?=\S)", re.I)


def titre_film(titre: str) -> str:
    """Le titre du film seul : « Movie Night: UN FILS » → « UN FILS ». Inchangé s'il ne reste rien de net."""
    reste = _PREFIXE_FILM.sub("", titre or "", count=1).strip(" «»\"'")
    return reste if len(re.findall(r"[^\W\d_]", reste)) >= 2 else titre


# Titre qui n'est qu'un genre ou une rubrique : il ne dit pas quel film, quelle expo, quel débat.
TITRES_GENERIQUES = re.compile(
    r"^\W*(?:une?\s+|la\s+|le\s+|les\s+)?(?:exposition|expo|exhibition|vernissage|cin[ée]ma(?: d.animation)?|film|projection|"
    r"cin[ée][- ]?club|movie night|tables? rondes?|conf[ée]rence|d[ée]bat|rencontre|atelier|lecture|concert|spectacle|"
    r"soir[ée]e|programme|agenda|[ée]v[ée]nement|activit[ée]s?|festival|journ[ée]es?|diffusion des savoirs|"
    r"sp[ée]cial \w+|nouveaut[ée]s?|à l.affiche|cette semaine|save the date|coming soon|bient[ôo]t|à venir)"
    r"(?:\s+(?:du mois|de la semaine|\d{4}))?\W*$", re.I)


def titre_generique(titre: str) -> bool:
    return bool(TITRES_GENERIQUES.match(titre or ""))


# Annonces de service : horaires, fermeture, recrutement… ce ne sont pas des événements.
_PAS_UN_EVENEMENT = re.compile(
    r"\b(?:ouvre|ouverture|ouverte|ferm[ée]e?s?|fermeture)\s+(?:exceptionnel|ses portes le|le dimanche|ce dimanche)|"
    r"horaires? d.ouverture|fermeture (?:exceptionnelle|annuelle)|\bappel [àa] (?:candidatures?|projets?|participation)|"
    r"\bcall for (?:applications|entries|artists|papers)|\brecrute\b|\brecrutement\b|offre d.emploi|"
    r"inscriptions? (?:ouvertes|aux cours)|entr[ée]e gratuite (?:aux|dans les) (?:sites|mus[ée]es)|\bjoyeux anniversaire\b|\bbonne f[êe]te\b|\bAïd moubarak\b", re.I)


# « L'Institut est fier d'être partenaire de la 8e édition de la Biennale… » : c'est l'annonce d'un partenariat,
# pas un événement ; l'événement lui-même (expositions, concerts) a ses propres fiches.
_PARTENARIAT = re.compile(r"\b(?:fi[eè]re?s?|heureu[xs]e?s?|ravie?s?|honor[ée]e?s?)\s+(?:d.[êe]tre|de compter parmi)\s+(?:les\s+)?partenaires?\b|"
                          r"\best\s+partenaire\s+(?:de la|du|des)\s+(?:\d+\S*\s+)?(?:[ée]dition|festival|biennale)|"
                          r"\ben partenariat avec\s+(?:la|le)\s+(?:biennale|festival)\b.{0,60}\bnous\s+(?:soutenons|accompagnons)", re.I)


def annonce_de_partenariat(notice: str) -> bool:
    """Vrai si le début de la notice dit que la structure est seulement partenaire de la manifestation."""
    return bool(_PARTENARIAT.search((notice or "")[:400].replace("’", "'")))


_HORS_CULTURE: re.Pattern | None = None


def _hors_culture() -> re.Pattern:
    """Mots de `_data/hors_culture.yml` (santé, prévention, caritatif…), lus une fois."""
    global _HORS_CULTURE
    if _HORS_CULTURE is None:
        import yaml
        try:
            mots = (yaml.safe_load((RACINE / "_data" / "hors_culture.yml").read_text()) or {}).get("mots") or []
        except OSError:
            mots = []
        motifs = [re.escape(unicodedata.normalize("NFKD", str(m).lower()).encode("ascii", "ignore").decode()) for m in mots]
        _HORS_CULTURE = re.compile("|".join(motifs) if motifs else "$^")
    return _HORS_CULTURE


def pas_un_evenement(titre: str) -> bool:
    """Vrai pour une annonce de service (« la Médiathèque ouvre exceptionnellement… ») ou qui n'est
    pas de la culture (santé, prévention : `_data/hors_culture.yml`)."""
    if _PAS_UN_EVENEMENT.search(titre or ""):
        return True
    simple = unicodedata.normalize("NFKD", (titre or "").lower().replace("’", "'")).encode("ascii", "ignore").decode()
    return bool(_hors_culture().search(simple))


# Langue de l'événement, seulement quand l'annonce la donne clairement : « pièce en arabe », « en langue
# française », « VOSTFR », ou un titre qui finit par « en français ». « Traduire le savoir en arabe » ne compte pas.
_EVT = r"(?:spectacle|pi[èe]ce|conf[ée]rence|lecture|film|projection|d[ée]bat|rencontre|atelier|visite|s[ée]ance|conte|table ronde)s?"
_LANGUES = [
    ("ar", r"en langue arabe|en dialecte tunisien|en darija|باللغة العربية|بالدارجة|باللهجة التونسية|"
           rf"{_EVT}(?: \S+){{0,3}} en (?:arabe|tunisien)\b"),
    ("fr", r"en langue fran[çc]aise|version fran[çc]aise|\bVF\b|باللغة الفرنسية|"
           rf"{_EVT}(?: \S+){{0,3}} en fran[çc]ais\b"),
    ("en", r"in english|en langue anglaise|باللغة الإنجليزية|"
           rf"{_EVT}(?: \S+){{0,3}} en anglais\b"),
    ("vo", r"\bVOST(?:FR|A)?\b|version originale"),
]
_FIN_TITRE = {"ar": r"en (?:arabe|tunisien)\s*$", "fr": r"en fran[çc]ais\s*$", "en": r"(?:en anglais|in english)\s*$"}


def langues_annoncees(titre: str, *textes: str) -> list[str]:
    t = " ".join(x or "" for x in (titre, *textes))
    return [code for code, motif in _LANGUES
            if re.search(motif, t, re.I)
            or (":" not in (titre or "") and re.search(_FIN_TITRE.get(code, "$^"), titre or "", re.I))]
