"""Programmes publiés en image sur une page Facebook (cinémas surtout), via Apify.

Beaucoup de salles ne créent pas d'événements Facebook : elles publient chaque
semaine une image avec le programme. Ce scraper récupère les dernières
publications avec image, enregistre les images dans le site, et lit le texte
des images :
- « ocr_facebook » : le texte que Facebook a lui-même lu sur l'image (fourni par Apify) ;
- « ocr » : le texte lu par Tesseract (OCR libre), s'il est installé.

La page Cinéma affiche l'image, le texte et le lien vers la publication.
L'étape suivante sera d'écrire, pour chaque salle, un lecteur de ce texte qui
en tire les films et les séances (les programmes ont un format récurrent).

Clé : variable d'environnement APIFY_TOKEN (voir facebook.py).

Options :
  page     nom de la page (facebook.com/<page>)
  max      nombre de publications avec image à garder (défaut 3)
  jours    garder les publications de moins de N jours (défaut 21) ; Apify ne relit que
           celles parues depuis la dernière lecture, les autres viennent du cache
  lecteur  comment tirer les films du programme (voir scrapers/lecteurs.py) :
           liste_films (une ligne « 🎬 Titre » par film), un_film_par_affiche
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess

from .. import lecteurs
from ..commun import RACINE, EnAttente, Publication, _session, propre
from .facebook import appeler_apify, _date

ACTEUR = "apify/facebook-posts-scraper"
DOSSIER_IMAGES = RACINE / "assets" / "programmes"
CACHE = RACINE / "_cache" / "publications"
LARGEUR_MAX = 1400


# Apify facture chaque publication lue, même déjà vue. On ne demande donc que les publications
# parues depuis la dernière lecture réussie (+ 2 jours de marge) ; les plus anciennes, encore
# dans la fenêtre « jours », sont reprises du cache _cache/publications/<source>.json.
def fenetre(source: dict) -> int:
    """Nombre de jours de publications à demander à Apify."""
    from ..ecriture import lire_etat
    jours = (source.get("options") or {}).get("jours", 21)
    if not (CACHE / f"{source['id']}.json").exists():
        return jours
    e = lire_etat().get(source["id"]) or {}
    if not (e.get("ok") and e.get("dernier_succes")):
        return jours
    ecart = (dt.datetime.now() - dt.datetime.fromisoformat(e["dernier_succes"])).days
    return min(jours, ecart + 2)


def en_cache(source: dict) -> dict[str, Publication]:
    """{lien : publication} lues aux passages précédents."""
    try:
        liste = json.loads((CACHE / f"{source['id']}.json").read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {p["lien"]: Publication(**p) for p in liste if isinstance(p, dict) and p.get("lien")}


def fusionner(source: dict, nouvelles: list[Publication], n_max: int) -> list[Publication]:
    """Nouvelles publications + celles du cache encore dans la fenêtre, les plus récentes d'abord."""
    jours = (source.get("options") or {}).get("jours", 21)
    limite = (dt.date.today() - dt.timedelta(days=jours)).isoformat()
    vues = {p.lien for p in nouvelles}
    anciennes = [p for p in en_cache(source).values()
                 if p.lien not in vues and (p.date or "") >= limite and all((RACINE / c).exists() for c in p.images)]
    toutes = sorted(nouvelles + anciennes, key=lambda p: p.date or "", reverse=True)[:n_max]
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{source['id']}.json").write_text(
        json.dumps([p.en_dict() for p in toutes], ensure_ascii=False, indent=1) + "\n")
    return toutes


def nettoyer_images(dossier, publications: list[Publication]) -> None:
    """Supprime les images des publications qui ne sont plus gardées."""
    gardees = {c.rsplit("/", 1)[-1] for p in publications for c in p.images}
    for f in dossier.iterdir():
        if f.name not in gardees:
            f.unlink()


def images_de(item: dict) -> list[tuple[str, str]]:
    """(url de l'image, texte lu par Facebook) pour chaque photo de la publication."""
    sortie = []
    for m in item.get("media") or []:
        if not isinstance(m, dict):
            continue
        if m.get("__typename", "Photo") != "Photo":
            continue  # vidéos : pas de programme lisible
        photo = m.get("photo_image") if isinstance(m.get("photo_image"), dict) else {}
        uri = photo.get("uri") or m.get("thumbnail")
        if uri:
            sortie.append((uri, propre(m.get("ocrText") or "")))
    return sortie


def enregistrer_image(url: str, dossier, nom: str) -> str:
    """Télécharge l'image une seule fois (même nom = même publication), réduite et en JPEG."""
    chemin = dossier / f"{nom}.jpg"
    if not chemin.exists():
        r = _session.get(url, timeout=60)
        r.raise_for_status()
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            if img.width > LARGEUR_MAX:
                img = img.resize((LARGEUR_MAX, round(img.height * LARGEUR_MAX / img.width)))
            img.save(chemin, "JPEG", quality=82)
        except ImportError:
            chemin.write_bytes(r.content)
    return str(chemin.relative_to(RACINE))


def lire_image(chemin) -> str:
    """Texte de l'image par Tesseract (français + arabe + anglais), vide s'il n'est pas installé."""
    if not shutil.which("tesseract"):
        return ""
    langues = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split()
    l = "+".join(x for x in ("fra", "ara", "eng") if x in langues) or "eng"
    r = subprocess.run(["tesseract", str(chemin), "stdout", "-l", l, "--psm", "4"],
                       capture_output=True, text=True, timeout=120)
    return "\n".join(ligne.strip() for ligne in r.stdout.splitlines() if ligne.strip())


def recuperer(source: dict) -> list:
    """Les dernières publications avec image, et les films qu'un lecteur y trouve."""
    publications = lire_publications(source)
    for p in publications:  # dans le journal, pour régler le lecteur
        print(f"    {p.date} | {' '.join(p.texte.split())[:110]} | ocr: {' '.join((p.ocr_facebook or p.ocr).split())[:80]}")
    lecteur = lecteurs.LECTEURS.get(source.get("options", {}).get("lecteur", ""))
    if not lecteur:
        return publications
    lieu = source.get("options", {}).get("lieu") or source["nom"]
    if lecteur is lecteurs.une_affiche_par_evenement:
        # Lieux et artistes (pas un cinéma) : seuls les événements lus vont sur le site.
        evts = [e for e in lecteur([p.en_dict() for p in publications], [], lieu) if e]
        for e in evts:
            e.categorie = source.get("categorie", e.categorie)
        print(f"  {source['id']} : {len(evts)} événement(s) lu(s) sur les affiches")
        return evts
    films = [f for f in lecteur([p.en_dict() for p in publications], lecteurs.titres_connus(), lieu) if f]
    print(f"  {source['id']} : {len(films)} film(s) lu(s) sur le programme")
    return publications + films


def lire_publications(source: dict) -> list[Publication]:
    cle = (os.environ.get("APIFY_TOKEN") or "").strip()  # un secret collé finit souvent par un retour à la ligne
    if not cle:
        raise EnAttente("clé APIFY_TOKEN pas encore configurée")
    o = source.get("options", {})
    page = o.get("page") or source["url"]
    url = page if page.startswith("http") else f"https://www.facebook.com/{page}"
    items = appeler_apify(o.get("acteur", ACTEUR), {
        "startUrls": [{"url": url}], "resultsLimit": o.get("resultats", 12),
        "onlyPostsNewerThan": f"{fenetre(source)} days"}, cle)
    if not isinstance(items, list):
        raise RuntimeError(f"réponse Apify inattendue : {str(items)[:200]}")
    erreurs = [i for i in items if i.get("error") and i.get("error") != "no_items"]  # no_items : rien de récent, pas une panne
    avec_image = [i for i in items if not i.get("error") and images_de(i)]
    print(f"  {source['id']} : {len(items)} publication(s) lue(s), {len(avec_image)} avec image")
    if items:  # nom de la page, pour reconnaître une page donnée par son seul numéro
        u = items[0].get("user") if isinstance(items[0].get("user"), dict) else {}
        print(f"    page : {items[0].get('pageName') or u.get('name') or '?'}")
    if erreurs and not avec_image:
        raise RuntimeError(f"Apify : {str(erreurs[0])[:250]}")
    avec_image.sort(key=lambda i: i.get("time") or "", reverse=True)

    dossier = DOSSIER_IMAGES / source["id"]
    dossier.mkdir(parents=True, exist_ok=True)
    publications, cache = [], en_cache(source)
    for item in avec_image[:o.get("max", 3)]:
        lien = item.get("topLevelUrl") or item.get("url") or url
        if lien in cache and cache[lien].images and all((RACINE / c).exists() for c in cache[lien].images):
            publications.append(cache[lien])  # déjà lue : ni téléchargement ni OCR
            continue
        debut = _date(item.get("time") or item.get("timestamp"))
        chemins, ocr_fb, ocr = [], [], []
        for n, (uri, texte_fb) in enumerate(images_de(item)[:4]):
            nom = hashlib.sha1(f"{lien}#{n}".encode()).hexdigest()[:12]
            try:
                chemin = enregistrer_image(uri, dossier, nom)
            except Exception as exc:  # noqa: BLE001 — une image injoignable ne bloque pas la source
                print(f"  image illisible ({exc.__class__.__name__}) : {lien}")
                continue
            chemins.append(chemin)
            if texte_fb:
                ocr_fb.append(texte_fb)
            ocr.append(lire_image(RACINE / chemin))
        publications.append(Publication(
            lien=lien, date=debut.date().isoformat() if debut else "",
            texte=(item.get("text") or "").strip(), images=chemins,
            ocr_facebook="\n\n".join(ocr_fb), ocr="\n\n".join(t for t in ocr if t)))
    publications = fusionner(source, publications, o.get("max", 3))
    nettoyer_images(dossier, publications)
    return publications

