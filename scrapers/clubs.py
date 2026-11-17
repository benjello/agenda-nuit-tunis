"""Clubs, discothèques, bars, pubs et restaurants ouverts tard en Tunisie, avec leurs horaires, pour la page /clubs/.

Ce sont les lieux de sortie « habituels » : ils ouvrent chaque semaine, même sans soirée spéciale annoncée.
Source : OpenStreetMap (Overpass, licence ODbL), complété et corrigé à la main par `_data/clubs.yml`.
Écrit `_data/clubs.json`. Relu une fois par semaine (les lieux changent peu).

Usage : python3 -m scrapers.clubs [--force]
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys

import yaml

from .commun import RACINE
from .enrichir import _overpass
from .villes import ville

FICHIER = RACINE / "_data" / "clubs.json"
MANUEL = RACINE / "_data" / "clubs.yml"
JOURS_ENTRE_DEUX = 7
VERSION = 3  # à augmenter quand on lit un nouveau champ : la liste est alors relue tout de suite

REQUETE = """[out:json][timeout:120];
area["ISO3166-1"="TN"][admin_level=2]->.tn;
(
  nwr["amenity"~"^(nightclub|bar|pub|karaoke_box)$"](area.tn);
  nwr["amenity"="restaurant"]["cuisine"~"cabaret"](area.tn);
  nwr["amenity"="restaurant"]["opening_hours"](area.tn);
);
out tags center;"""

# amenity OpenStreetMap → type affiché sur la page (même clés que _data/categories.yml)
TYPES = {"nightclub": "club", "bar": "bar", "pub": "bar", "karaoke_box": "karaoke", "restaurant": "cabaret"}
# Un restaurant (hors cabaret) n'est gardé que s'il ferme à 22 h ou plus tard : type « restaurant » ;
# s'il ferme avant 23 h, la page le signale (« ferme à 22h30 »)
# (_data/types_clubs.yml, propre à la page /clubs/, pas une catégorie d'événement).
SOIR = 22
TARD = 23


# Valeurs OpenStreetMap de cuisine=* → (français, anglais). Une valeur inconnue est gardée telle quelle.
CUISINES = {
    "regional": ("tunisienne", "Tunisian"), "local": ("tunisienne", "Tunisian"), "tunisian": ("tunisienne", "Tunisian"),
    "oriental": ("orientale", "Middle Eastern"), "lebanese": ("libanaise", "Lebanese"), "turkish": ("turque", "Turkish"),
    "moroccan": ("marocaine", "Moroccan"), "arab": ("arabe", "Arab"), "mediterranean": ("méditerranéenne", "Mediterranean"),
    "italian": ("italienne", "Italian"), "pizza": ("pizza", "pizza"), "pasta": ("pâtes", "pasta"),
    "french": ("française", "French"), "fine_dining": ("gastronomique", "fine dining"), "european": ("européenne", "European"),
    "international": ("internationale", "international"), "spanish": ("espagnole", "Spanish"), "greek": ("grecque", "Greek"),
    "seafood": ("poisson et fruits de mer", "seafood"), "fish": ("poisson", "fish"), "octopus": ("poulpe", "octopus"),
    "steak_house": ("grillades", "steakhouse"), "barbecue": ("grillades", "barbecue"), "grill": ("grillades", "grill"),
    "burger": ("burgers", "burgers"), "chicken": ("poulet", "chicken"), "kebab": ("kebab", "kebab"),
    "sandwich": ("sandwichs", "sandwiches"), "salad": ("salades", "salads"), "dessert": ("desserts", "desserts"),
    "japanese": ("japonaise", "Japanese"), "sushi": ("sushis", "sushi"), "asian": ("asiatique", "Asian"),
    "chinese": ("chinoise", "Chinese"), "thai": ("thaïe", "Thai"), "indian": ("indienne", "Indian"),
    "mexican": ("mexicaine", "Mexican"), "american": ("américaine", "American"), "noodle": ("nouilles", "noodles"),
    "coffee_shop": ("café", "coffee shop"), "tapas": ("tapas", "tapas"), "vegetarian": ("végétarienne", "vegetarian"),
}


def cuisine(valeur: str, langue: str = "fr") -> str:
    """« seafood;pizza;regional » → « poisson et fruits de mer, pizza, tunisienne » (sans doublon)."""
    i = 1 if langue == "en" else 0
    mots = [CUISINES.get(v.strip().lower(), (v.strip().replace("_", " "),) * 2)[i] for v in (valeur or "").split(";") if v.strip()]
    return ", ".join(dict.fromkeys(mots))


def lien_menu(t: dict) -> str:
    """Lien vers la carte, s'il est dans OpenStreetMap (website:menu, menu:url…)."""
    for k in ("website:menu", "menu:url", "contact:menu", "url:menu", "menu"):
        if str(t.get(k, "")).startswith("http"):
            return t[k]
    return ""


def fermeture(oh: str) -> tuple[int, int] | None:
    """Heure de fermeture la plus tardive (h, min), après minuit comptée 24 h et plus ; None si inconnue."""
    if "24/7" in (oh or ""):
        return (48, 0)
    plus_tard = None
    for dh, fh, fm in re.findall(r"(\d{1,2}):\d{2}\s*-\s*(\d{1,2}):(\d{2})", oh or ""):
        dh, fh, fm = int(dh), int(fh), int(fm)
        if fh < dh or (fh == 0 and fm == 0):
            fh += 24
        plus_tard = max(plus_tard or (fh, fm), (fh, fm))
    return plus_tard


def ouvert_le_soir(oh: str) -> bool:
    """Vrai si une plage d'horaires OpenStreetMap finit à 22 h ou plus tard (ou après minuit)."""
    f = fermeture(oh)
    return bool(f and f[0] >= SOIR)


def ferme_tot(oh: str) -> str:
    """« 22h30 » pour un lieu qui ferme entre 22 h et 23 h (affiché sur la page), sinon ""."""
    f = fermeture(oh)
    return f"{f[0]}h{f[1]:02d}".replace("h00", "h") if f and SOIR <= f[0] < TARD else ""

GENERIQUE = re.compile(r"(?i)\s*(bar|pub|disco(th[eè]que)?|night ?club|club|after work|ملهى ليلي|حانة)\s*")

# Ce qu'OpenStreetMap range parfois en « bar » mais qui n'est pas une sortie de nuit : cafés, restaurants,
# salles des fêtes, bars d'hôtel réservés aux clients (piscine, hall), noms de ville seuls.
HORS_SUJET = re.compile(r"(?i)\bcaf[ée]s?\b|coffee|\bsalon\b|\brestaurant\b|\bpizz|\bsnack|\bp[âa]tisserie|\bglacier\b"
                        r"|\bpool bar\b|\blobby\b|\bh[ôo]tel\b|\bespace\b|^\s*(tozeur|djerba|sousse|monastir|tunis|sfax|nabeul|hammamet)\s*$"
                        r"|مقهى|قهوة|مطعم")

def hors_sujet(nom: str) -> bool:
    """Vrai pour un café, un restaurant, un bar d'hôtel… Un « café-bar » (brasserie de Tunis) reste un bar."""
    if re.search(r"(?i)\bcaf[ée]\b", nom) and re.search(r"(?i)\bbar\b", nom) and not re.search(r"(?i)h[ôo]tel|restaurant", nom):
        return False
    return bool(HORS_SUJET.search(nom))


_JOURS = {
    "fr": {"Mo": "lun", "Tu": "mar", "We": "mer", "Th": "jeu", "Fr": "ven", "Sa": "sam", "Su": "dim", "PH": "fériés"},
    "en": {"Mo": "Mon", "Tu": "Tue", "We": "Wed", "Th": "Thu", "Fr": "Fri", "Sa": "Sat", "Su": "Sun", "PH": "holidays"},
    "ar": {"Mo": "الإثنين", "Tu": "الثلاثاء", "We": "الأربعاء", "Th": "الخميس", "Fr": "الجمعة", "Sa": "السبت", "Su": "الأحد", "PH": "الأعياد"},
}
_MOTS = {
    "fr": {"24/7": "tous les jours, 24 h/24", "off": "fermé"},
    "en": {"24/7": "every day, 24/7", "off": "closed"},
    "ar": {"24/7": "كل يوم، 24/24", "off": "مغلق"},
}


def horaires_fr(oh: str, langue: str = "fr") -> str:
    """« Th-Sa 23:00-05:00; Su off » → « jeu-sam 23h-5h ; dim fermé » (ou en anglais, en arabe). Le reste est gardé."""
    if not oh:
        return ""
    jours, mots = _JOURS[langue], _MOTS[langue]
    t = oh.replace("24/7", mots["24/7"])
    t = re.sub(r"\b(Mo|Tu|We|Th|Fr|Sa|Su|PH)\b", lambda m: jours[m.group(1)], t)
    if langue == "fr":
        t = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: f"{int(m.group(1))}h" + ("" if m.group(2) == "00" else m.group(2)), t)
    t = re.sub(r"\boff\b", mots["off"], t)
    return re.sub(r"\s*;\s*", " ; " if langue == "fr" else "; ", t).strip()


# Régions de _data/villes.yml par coordonnées (plus sûr que le nom : sans adresse, ville() répond « tunis »).
_ZONES = [  # (région, lat min, lat max, lon min, lon max), la première qui contient le point gagne
    ("bizerte", 37.05, 37.6, 9.4, 10.3),
    ("tunis", 36.6, 37.05, 9.9, 10.45),
    ("nabeul", 36.2, 37.1, 10.45, 11.2),
    ("sousse", 35.7, 36.2, 10.2, 10.75),
    ("monastir", 35.0, 35.8, 10.5, 11.2),
    ("sfax", 34.4, 35.0, 10.3, 11.4),
    ("sud", 30.0, 34.4, 7.5, 11.7),
]


def region(lat, lon, *textes: str) -> str:
    if lat is not None and lon is not None:
        for nom, a, b, c, d in _ZONES:
            if a <= lat <= b and c <= lon <= d:
                return nom
        return "autres"
    return ville(*textes)


def depuis_osm(elements: list[dict]) -> list[dict]:
    lieux = []
    for el in elements:
        t = el.get("tags") or {}
        nom = (t.get("name:fr") or t.get("name") or t.get("name:en") or "").strip()
        restaurant = t.get("amenity") == "restaurant" and "cabaret" not in (t.get("cuisine") or "")
        if restaurant:
            if not nom or re.fullmatch(r"(?i)\s*(restaurant|مطعم)\s*", nom) or not ouvert_le_soir(t.get("opening_hours", "")):
                continue
        elif not nom or GENERIQUE.fullmatch(nom) or hors_sujet(nom):  # « Discotheque », « Go Café », « Pool Bar »
            continue
        adresse = ", ".join(x for x in (
            " ".join(y for y in (t.get("addr:housenumber"), t.get("addr:street")) if y),
            t.get("addr:suburb") or t.get("addr:place"), t.get("addr:city")) if x)
        centre = el.get("center") or el
        insta = t.get("contact:instagram") or t.get("instagram") or ""
        lieux.append({
            "nom": nom,
            "type": "restaurant" if restaurant else TYPES.get(t.get("amenity"), "bar"),
            "ville": region(centre.get("lat"), centre.get("lon"), nom, adresse, t.get("addr:city", "")),
            "adresse": adresse,
            "horaires": horaires_fr(t.get("opening_hours", "")),
            "horaires_en": horaires_fr(t.get("opening_hours", ""), "en"),
            "horaires_ar": horaires_fr(t.get("opening_hours", ""), "ar"),
            "site": t.get("website") or t.get("contact:website") or "",
            "instagram": insta.rstrip("/").split("/")[-1].lstrip("@") if insta else "",
            "facebook": t.get("contact:facebook") or t.get("facebook") or "",
            "telephone": t.get("phone") or t.get("contact:phone") or "",
            "lat": centre.get("lat"), "lon": centre.get("lon"),
            "osm": f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}",
            # Ambiance : style de musique (music:genre, peu rempli) et terrasse ; le reste vient de clubs.yml.
            "ferme": ferme_tot(t.get("opening_hours", "")) if restaurant else "",
            "cuisine": cuisine(t.get("cuisine", "")) if restaurant else "",
            "cuisine_en": cuisine(t.get("cuisine", ""), "en") if restaurant else "",
            "menu": lien_menu(t),
            "ambiance": ", ".join(x for x in ((t.get("music:genre") or t.get("music") or "").replace(";", ", "),
                                              "terrasse" if t.get("outdoor_seating") == "yes" else "") if x),
            "age_min": t.get("min_age", ""),
        })
    return lieux


def fusionner(osm: list[dict], manuel: list[dict]) -> list[dict]:
    """Les entrées de clubs.yml corrigent celles d'OpenStreetMap (même nom) ou s'y ajoutent."""
    cle = lambda n: re.sub(r"[^a-z0-9]", "", (n or "").lower())  # noqa: E731
    par_nom = {cle(x["nom"]): x for x in osm}
    for m in manuel or []:
        if m.get("cacher"):
            par_nom.pop(cle(m.get("nom")), None)
            continue
        base = par_nom.get(cle(m.get("nom")), {"nom": m.get("nom"), "type": "club", "ville": ville(m.get("nom", ""), m.get("adresse", ""))})
        base.update({k: v for k, v in m.items() if v not in (None, "")})
        base["manuel"] = True
        par_nom[cle(base["nom"])] = base
    lieux = [{k: v for k, v in x.items() if v not in (None, "")} for x in par_nom.values()]  # champs vides retirés : la page n'affiche que ce qu'on sait
    return sorted(lieux, key=lambda x: (x.get("ville", ""), x.get("type", ""), x["nom"].lower()))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        ancien = json.loads(FICHIER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        ancien = {}
    if ancien.get("lu_le") and ancien.get("version") == VERSION and "--force" not in argv:
        age = (dt.date.today() - dt.date.fromisoformat(ancien["lu_le"])).days
        if age < JOURS_ENTRE_DEUX:
            print(f"clubs : liste lue il y a {age} jour(s), pas de nouvelle lecture.")
            return 0
    manuel = yaml.safe_load(MANUEL.read_text()) if MANUEL.exists() else []
    try:
        osm = depuis_osm(_overpass(REQUETE))
    except Exception as exc:  # noqa: BLE001 — Overpass saturé : on garde l'ancienne liste
        print(f"clubs : OpenStreetMap illisible ({exc}), ancienne liste gardée.")
        return 0
    avant = sum(1 for x in ancien.get("lieux") or [] if not x.get("manuel"))
    if len(osm) < avant / 2:  # réponse vide ou tronquée d'Overpass (délai dépassé) : on ne vide pas la page
        print(f"clubs : OpenStreetMap n'a renvoyé que {len(osm)} lieu(x) contre {avant} avant, ancienne liste gardée.")
        return 0
    lieux = fusionner(osm, manuel)
    FICHIER.write_text(json.dumps({"lu_le": dt.date.today().isoformat(), "version": VERSION, "source": "OpenStreetMap (ODbL) et _data/clubs.yml",
                                   "lieux": lieux}, ensure_ascii=False, indent=1))
    avec_insta = [x for x in lieux if x.get("instagram")]
    print(f"clubs : {len(lieux)} lieu(x), dont {sum(bool(x.get('horaires')) for x in lieux)} avec horaires "
          f"et {len(avec_insta)} avec un compte Instagram (sources possibles) :")
    for x in avec_insta:
        print(f"  - @{x['instagram']} | {x['nom']} | {x['ville']} | {x['type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
