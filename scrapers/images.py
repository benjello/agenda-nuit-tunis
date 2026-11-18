"""Images d'événements : copie dans le dépôt, réparation, remplacement. Après chaque passage des scrapers.

Une vignette dont l'image ne charge pas laissait un cadre vide sur la carte. Pour chaque ligne
« image: » des événements, ce script :
1. vérifie l'image (HTTP 200, type image, signature ; sans référent, comme le navigateur du lecteur) ;
2. si elle marche, en garde une copie dans assets/images/ et pointe la fiche vers cette copie :
   les liens qui expirent (Instagram, Facebook, billetterie) ne cassent plus la carte ;
3. si elle est cassée, cherche la vraie image de l'événement : le visuel de la page de l'annonce
   (og:image, schema.org), celui de ses autres sources, la même affiche sur une autre fiche ; en dernier
   recours seulement : la photo du lieu (profil du club dans _data/fiches_clubs.json, sinon Wikimedia
   Commons via _data/enrichi.json), puis l'illustration
   de la catégorie (assets/categories/*.svg). Aucune carte ne reste avec un cadre vide.
Une panne passagère (délai dépassé, 5xx) attend CASSEE_APRES passages avant de remplacer ; une
vraie erreur (404, 403, page HTML) remplace tout de suite. L'image d'origine est réessayée à
chaque passage : si elle revient, elle reprend sa place. Les images qui marchent ne sont relues
que tous les JOURS_RELECTURE jours. Bilan et cache dans _data/images.json.

  python3 -m scrapers.images
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .commun import ENTETES, RACINE, slug

CACHE = RACINE / "_data" / "images.json"
DOSSIER = RACINE / "assets" / "images"
CASSEE_APRES = 2      # passages ratés (panne passagère) avant de remplacer l'image
JOURS_RELECTURE = 7   # une image qui marche est relue une fois par semaine
TAILLE_MAX = 2_000_000
LIGNE_IMAGE = re.compile(r'^image:[ \t]*"?([^"\n]*)"?[ \t]*\n', re.M)
SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF", b"<svg", b"<?xml")  # jpeg, png, gif, webp, svg
EXTENSIONS = {"jpeg": "jpg", "jpg": "jpg", "png": "png", "gif": "gif", "webp": "webp", "svg+xml": "svg", "avif": "avif"}


def est_une_image(debut: bytes) -> bool:
    return any(debut.startswith(s) for s in SIGNATURES) or debut[4:12] in (b"ftypavif", b"ftypheic")


def recuperer(url: str) -> tuple[str, str, bytes, str]:
    """(état, détail, octets, extension) ; état : ok, cassee (erreur sûre) ou incertaine (panne passagère)."""
    entetes = {**ENTETES, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    try:
        r = requests.get(url, headers=entetes, timeout=20, stream=True)
    except requests.RequestException as exc:
        return "incertaine", type(exc).__name__, b"", ""
    try:
        if r.status_code >= 500 or r.status_code == 429:
            return "incertaine", f"HTTP {r.status_code}", b"", ""
        if r.status_code != 200:
            return "cassee", f"HTTP {r.status_code}", b"", ""
        type_ = r.headers.get("Content-Type", "").lower()
        if not type_.startswith("image/"):
            return "cassee", "pas une image : " + type_[:40], b"", ""
        octets = b""
        for morceau in r.iter_content(65536):
            octets += morceau
            if len(octets) > TAILLE_MAX:
                return "ok", "trop lourde pour être copiée", b"", ""
        if not est_une_image(octets[:64]):
            return "cassee", "contenu illisible", b"", ""
        ext = EXTENSIONS.get(type_.split("/")[1].split(";")[0].strip(), "jpg")
        return "ok", "", octets, ext
    except requests.RequestException as exc:
        return "incertaine", type(exc).__name__, b"", ""
    finally:
        r.close()


def verifier_locale(chemin: str) -> tuple[str, str]:
    f = RACINE / chemin
    if not f.is_file():
        return "cassee", "fichier absent"
    return ("ok", "") if est_une_image(f.read_bytes()[:64]) else ("cassee", "fichier illisible")


def copier(url: str, octets: bytes, ext: str) -> str:
    """Enregistre l'image dans assets/images/ ; renvoie son chemin relatif."""
    DOSSIER.mkdir(parents=True, exist_ok=True)
    chemin = f"assets/images/{hashlib.sha1(url.encode()).hexdigest()[:12]}.{ext}"
    (RACINE / chemin).write_bytes(octets)
    return chemin


def images_de_la_page(lien: str) -> list[str]:
    """Images que la page de l'annonce désigne comme son visuel : og:image, twitter:image,
    image_src, image du schema.org (JSON-LD). Les plus fiables d'abord."""
    trouvees: list[str] = []
    try:
        r = requests.get(lien, headers=ENTETES, timeout=20)
        if r.status_code != 200 or "html" not in r.headers.get("Content-Type", ""):
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        for nom in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
            for m in soup.find_all("meta", attrs={"property": nom}) + soup.find_all("meta", attrs={"name": nom}):
                if m.get("content"):
                    trouvees.append(m["content"].strip())
        for l in soup.find_all("link", rel="image_src"):
            if l.get("href"):
                trouvees.append(l["href"].strip())
        for sc in soup.find_all("script", type="application/ld+json"):
            try:
                donnees = json.loads(sc.string or "")
            except ValueError:
                continue
            for d in (donnees if isinstance(donnees, list) else [donnees]):
                img = d.get("image") if isinstance(d, dict) else None
                for i in (img if isinstance(img, list) else [img]):
                    i = i.get("url") if isinstance(i, dict) else i
                    if isinstance(i, str):
                        trouvees.append(i.strip())
    except requests.RequestException:
        pass
    vues: list[str] = []
    for t in trouvees:
        t = urljoin(lien, t)
        if t.startswith("http") and t not in vues:
            vues.append(t)
    return vues


def a_relire(fiche: dict | None, maintenant: dt.datetime) -> bool:
    if not fiche or fiche.get("etat") != "ok":
        return True  # jamais vue, ou ratée : on réessaie à chaque passage
    return maintenant - dt.datetime.fromisoformat(fiche["verifiee"]) > dt.timedelta(days=JOURS_RELECTURE)


def mettre_a_jour(fiche: dict | None, etat: str, detail: str, maintenant: dt.datetime) -> dict:
    fiche = dict(fiche or {})
    fiche.update(etat=etat, detail=detail, verifiee=maintenant.isoformat(timespec="seconds"))
    fiche["echecs"] = 0 if etat == "ok" else fiche.get("echecs", 0) + 1
    return fiche


def a_remplacer(fiche: dict) -> bool:
    """Vraie erreur : tout de suite ; panne passagère : après CASSEE_APRES passages."""
    if fiche.get("etat") == "ok":
        return False
    return fiche["etat"] == "cassee" or fiche.get("echecs", 0) >= CASSEE_APRES


def remplacement_categorie(categorie: str) -> str:
    f = f"assets/categories/{categorie}.svg"
    return f if (RACINE / f).is_file() else "assets/categories/autre.svg"


def photo_du_lieu(lieu: str, cache: dict, enrichi: dict, clubs: dict | None = None) -> str:
    """Photo du lieu : profil du club déjà copié (assets/clubs/…), sinon Wikimedia Commons, ou ''."""
    cle = slug(lieu or "")
    for nom, fiche in (clubs or {}).items():
        photo = fiche.get("photo", "") if isinstance(fiche, dict) else ""
        if cle and slug(nom) == cle and photo and (RACINE / photo).is_file():
            return photo
    fiche = enrichi.get("images", {}).get("lieu:" + cle)
    if not fiche:
        return ""
    return image_copiee(fiche["image"], cache)


def image_copiee(url: str, cache: dict) -> str:
    """Copie locale d'une image externe, vérifiée ; '' si elle ne marche pas."""
    c = cache.get("copie:" + url)
    if c and (RACINE / c).is_file():
        return c
    etat, _, octets, ext = recuperer(url)
    if etat == "ok" and octets:
        cache["copie:" + url] = copier(url, octets, ext)
        return cache["copie:" + url]
    return ""


def champ(texte: str, nom: str) -> str:
    m = re.search(rf'^{nom}:[ \t]*"?([^"\n]*)"?[ \t]*$', texte, re.M)
    return m.group(1).strip() if m else ""


def remplacer_image(texte: str, chemin: str) -> str:
    return LIGNE_IMAGE.sub(lambda _: f'image: "{chemin}"\n', texte, count=1)


def main() -> int:
    maintenant = dt.datetime.now()
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    enrichi = json.loads((RACINE / "_data" / "enrichi.json").read_text()) if (RACINE / "_data" / "enrichi.json").exists() else {}
    f_clubs = RACINE / "_data" / "fiches_clubs.json"
    clubs = json.loads(f_clubs.read_text()) if f_clubs.exists() else {}
    fichiers = {}
    for f in (RACINE / "_events").rglob("*.md"):
        entete = f.read_text(encoding="utf-8").split("\n---", 2)[0] + "\n"
        m = LIGNE_IMAGE.search(entete)
        if m and m.group(1):
            fichiers[f] = m.group(1)
    urls = sorted(set(fichiers.values()))
    externes = [u for u in urls if "://" in u]
    # --- 1. vérifier (et copier) les images externes
    a_verifier = [u for u in externes if a_relire(cache.get(u), maintenant) or not (RACINE / cache[u].get("copie", "x")).is_file() and cache[u].get("etat") == "ok" and not cache[u].get("trop_lourde")]
    with ThreadPoolExecutor(8) as pool:
        for u, (etat, detail, octets, ext) in zip(a_verifier, pool.map(recuperer, a_verifier)):
            c = mettre_a_jour(cache.get(u), etat, detail, maintenant)
            c.pop("copie", None)
            c.pop("trop_lourde", None)
            if etat == "ok" and octets:
                c["copie"] = copier(u, octets, ext)
            elif etat == "ok":
                c["trop_lourde"] = True
            cache[u] = c
    # --- 2. fiches locales (assets/…) : le fichier doit exister
    for u in urls:
        if "://" not in u:
            etat, detail = verifier_locale(u)
            cache[u] = mettre_a_jour(None, etat, detail, maintenant)
    # --- 3. réécrire les fiches
    meme_titre: dict[str, str] = {}
    for f, u in fichiers.items():
        c = cache[u]
        bonne = c.get("copie") or (u if c["etat"] == "ok" and "://" not in u else "")
        if bonne:
            meme_titre.setdefault(slug(champ(f.read_text(encoding="utf-8").split("\n---", 2)[0], "title")), bonne)
    copiees = remplacees = 0
    bilan = {"copiees": 0, "lien": 0, "autre fiche": 0, "lieu": 0, "categorie": 0}
    for f, u in fichiers.items():
        c = cache[u]
        texte = f.read_text(encoding="utf-8")
        if c["etat"] == "ok":
            if c.get("copie"):
                f.write_text(remplacer_image(texte, c["copie"]), encoding="utf-8")
                bilan["copiees"] += 1
            continue
        if not a_remplacer(c):
            continue
        entete = texte.split("\n---", 2)[0]
        choix, origine = "", ""
        # a) le visuel de l'annonce : page du lien principal, puis des autres sources du même événement
        liens = [champ(entete, "link")] + re.findall(r'^\s+link:[ \t]*"?([^"\n]+)"?', entete, re.M)
        for lien in dict.fromkeys(l for l in liens if l.startswith("http")):
            cle = "lien:" + lien
            if cle in cache and (RACINE / cache[cle]).is_file():
                choix, origine = cache[cle], "lien"
                break
            for autre in images_de_la_page(lien):
                if autre != u and (choix := image_copiee(autre, cache)):
                    cache[cle], origine = choix, "lien"
                    break
            if choix:
                break
        # b) le même événement dans une autre source, avec une image qui marche
        if not choix:
            choix = meme_titre.get(slug(champ(entete, "title")), "")
            origine = "autre fiche"
        if not choix:
            choix = photo_du_lieu(champ(entete, "venue"), cache, enrichi, clubs)
            origine = "lieu"
        if not choix:
            choix, origine = remplacement_categorie(champ(entete, "category")), "categorie"
        f.write_text(remplacer_image(texte, choix), encoding="utf-8")
        bilan[origine] += 1
        remplacees += 1
        print(f"✗ {f.name} : {c['detail']} → {origine} ({choix})")
    # le cache ne garde que ce qui sert encore
    gardes = set(urls) | {k for k in cache if k.startswith(("copie:", "lien:"))}
    cache = {k: v for k, v in cache.items() if k in gardes}
    cache["_bilan"] = {"date": maintenant.isoformat(timespec="seconds"), "images": len(urls),
                       "cassees": sum(1 for u in urls if cache[u]["etat"] != "ok"), **bilan}
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Images : {len(urls)} distinctes, {len(a_verifier)} vérifiées, {cache['_bilan']['cassees']} cassées ; "
          f"{bilan['copiees']} copie(s) locale(s), remplacées : {bilan['lien']} par l'image de l'annonce, {bilan['autre fiche']} par une autre fiche du même événement, "
          f"{bilan['lieu']} par la photo du lieu, {bilan['categorie']} par l'illustration de la catégorie.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
