"""Traduction automatique des titres et des notices : français, arabe, anglais.

Outil libre et gratuit, sans service en ligne : les modèles d'Argos Translate
(https://github.com/argosopentech/argos-translate, licence MIT / CC0), lus directement avec
CTranslate2 et SentencePiece. Pas de PyTorch : l'installation reste légère.

Chaque texte est traduit une seule fois. Les traductions sont gardées dans
_data/traductions.json :
  titres   { titre d'origine : { en, ar, fr } }   (sans la langue d'origine)
  notices  { _events/…/x.md : { cle, en, ar, fr } } (cle : empreinte du texte d'origine)
Le site montre la traduction quand le lecteur choisit عربي ou EN (assets/site.js).

Pas de modèle direct entre le français et l'arabe : on passe par l'anglais.
Les titres de films, les noms propres d'un seul mot et les titres déjà bilingues
(« هروب | FUITE ») ne sont pas traduits.

  python3 -m scrapers.traduire            traduit ce qui est nouveau
  python3 -m scrapers.traduire --essai    traduit trois phrases (vérifier l'installation)
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import time
import zipfile
from pathlib import Path

import requests

from .commun import RACINE
from .doublons import _lire

FICHIER = RACINE / "_data" / "traductions.json"
DOSSIER_MODELES = Path(os.environ.get("MODELES_TRADUCTION", Path.home() / ".cache" / "agenda-traduction"))
MODELES = {
    ("fr", "en"): "https://argos-net.com/v1/translate-fr_en-1_9.argosmodel",
    ("en", "fr"): "https://argos-net.com/v1/translate-en_fr-1_9.argosmodel",
    ("en", "ar"): "https://argos-net.com/v1/translate-en_ar-1_0.argosmodel",
    ("ar", "en"): "https://argos-net.com/v1/translate-ar_en-1_0.argosmodel",
}
LANGUES = ("fr", "ar", "en")
MAX_TEXTES = 400          # textes nouveaux par passage (le reste attend le passage suivant)
MAX_SECONDES = 20 * 60

_ARABE = re.compile(r"[؀-ۿ]")
_LATIN = re.compile(r"[A-Za-zÀ-ÿ]")
_ANGLAIS = re.compile(r"\b(?:the|and|with|of|for|night|live|party|festival|session|in|at|by|from|your|you|our)\b", re.I)
_FRANCAIS = re.compile(r"\b(?:le|la|les|des|du|de|et|avec|pour|une|un|au|aux|sur|dans|en)\b", re.I)
_PHRASES = re.compile(r"(?<=[.!?؟…])\s+|\n+")


def langue(texte: str) -> str:
    ar, lat = len(_ARABE.findall(texte)), len(_LATIN.findall(texte))
    if ar > lat:
        return "ar"
    return "en" if len(_ANGLAIS.findall(texte)) > len(_FRANCAIS.findall(texte)) else "fr"


def a_traduire(titre: str) -> bool:
    """Un nom propre (« Hyperculte », « BAKMA ») ou un titre déjà bilingue n'a pas besoin de traduction."""
    if len(_ARABE.findall(titre)) >= 3 and len(_LATIN.findall(titre)) >= 3:
        return False
    mots = re.findall(r"[^\W\d_]{2,}", titre)
    return len(mots) >= 2


class Traducteur:
    def __init__(self, dossier: Path = DOSSIER_MODELES):
        import ctranslate2
        import sentencepiece
        self._ct, self._sp, self.dossier = ctranslate2, sentencepiece, dossier
        self._modeles: dict = {}

    def _modele(self, de: str, vers: str):
        if (de, vers) not in self._modeles:
            racine = self.dossier / f"{de}_{vers}"
            if not (racine / "ok").exists():
                print(f"  traduction : téléchargement du modèle {de} → {vers}")
                r = requests.get(MODELES[(de, vers)], timeout=300)
                r.raise_for_status()
                racine.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    z.extractall(racine)
                (racine / "ok").write_text("")
            modele = next(p.parent for p in racine.rglob("model.bin"))
            sp = next(racine.rglob("sentencepiece.model"))
            self._modeles[(de, vers)] = (self._ct.Translator(str(modele), device="cpu", compute_type="int8"),
                                         self._sp.SentencePieceProcessor(model_file=str(sp)))
        return self._modeles[(de, vers)]

    def _direct(self, phrases: list[str], de: str, vers: str) -> list[str]:
        if not phrases:
            return []
        trad, sp = self._modele(de, vers)
        jetons = [sp.encode(p, out_type=str) for p in phrases]
        res = trad.translate_batch(jetons, beam_size=2, max_decoding_length=256)
        # comme Argos : les jetons recollés, « ▁ » marquant les espaces
        return [re.sub(r"\s+", " ", "".join(r.hypotheses[0]).replace("▁", " ")).strip() for r in res]

    def traduire(self, textes: list[str], de: str, vers: str) -> list[str]:
        """Traduit une liste de textes, phrase par phrase ; fr ↔ ar passe par l'anglais."""
        if de == vers:
            return list(textes)
        if (de, vers) not in MODELES:
            return self.traduire(self.traduire(textes, de, "en"), "en", vers)
        decoupe = [[p for p in _PHRASES.split(t) if p.strip()] for t in textes]
        plat = self._direct([p for ps in decoupe for p in ps], de, vers)
        res, i = [], 0
        for t, ps in zip(textes, decoupe):
            res.append(" ".join(plat[i:i + len(ps)]) if "\n" not in t else "\n".join(plat[i:i + len(ps)]))
            i += len(ps)
        return res


def _cle(texte: str) -> str:
    return hashlib.sha1(texte.encode()).hexdigest()[:12]


def evenements() -> list[tuple[str, dict, str]]:
    res = []
    for f in sorted((RACINE / "_events").rglob("*.md")):
        if f.name == "README.md":
            continue
        champs, corps = _lire(f)
        if champs and not champs.get("doublon"):
            res.append((str(f.relative_to(RACINE)), champs, corps.strip()))
    return res


def lire() -> dict:
    try:
        d = json.loads(FICHIER.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        d = {}
    return {"titres": d.get("titres") or {}, "notices": d.get("notices") or {}}


def a_faire(evts: list, cache: dict) -> tuple[list, list]:
    """(titres, notices) qui n'ont pas encore de traduction."""
    titres, notices = [], []
    for chemin, c, corps in evts:
        t = str(c.get("title") or "").strip()
        if t and not c.get("film") and a_traduire(t) and t not in cache["titres"] and t not in titres:
            titres.append(t)
        if corps and len(re.findall(r"[^\W\d_]", corps)) >= 20:
            n = cache["notices"].get(chemin)
            if not n or n.get("cle") != _cle(corps):
                notices.append((chemin, corps))
    return titres, notices


def traduire_tout(traducteur, cache: dict, titres: list[str], notices: list) -> int:
    debut, n = time.monotonic(), 0
    # par langue d'origine : un lot par modèle, plus rapide
    for de in LANGUES:
        lot = [t for t in titres if langue(t) == de][:MAX_TEXTES]
        for vers in LANGUES:
            if vers != de and lot:
                for t, tr in zip(lot, traducteur.traduire(lot, de, vers)):
                    cache["titres"].setdefault(t, {})[vers] = tr
        n += len(lot)
        lot_n = [x for x in notices if langue(x[1]) == de][:MAX_TEXTES]
        for i in range(0, len(lot_n), 20):  # par paquets de 20 notices
            if time.monotonic() - debut > MAX_SECONDES:
                print("  traduction : temps écoulé, la suite au prochain passage")
                return n
            paquet = lot_n[i:i + 20]
            entrees = [{"cle": _cle(corps)} for _, corps in paquet]
            for vers in LANGUES:
                if vers != de:
                    for e, tr in zip(entrees, traducteur.traduire([corps for _, corps in paquet], de, vers)):
                        e[vers] = tr
            for (chemin, _), e in zip(paquet, entrees):
                cache["notices"][chemin] = e
            n += len(paquet)
    return n


def nettoyer(cache: dict, evts: list) -> None:
    """On ne garde que les traductions d'événements encore présents."""
    titres = {str(c.get("title") or "").strip() for _, c, _ in evts}
    chemins = {chemin for chemin, _, _ in evts}
    cache["titres"] = {k: v for k, v in sorted(cache["titres"].items()) if k in titres}
    cache["notices"] = {k: v for k, v in sorted(cache["notices"].items()) if k in chemins}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--essai", action="store_true", help="traduire trois phrases et s'arrêter")
    args = p.parse_args(argv)
    try:
        traducteur = Traducteur()
    except ImportError:
        print("traduction : installer ctranslate2 et sentencepiece (pip install -r requirements.txt)")
        return 0
    if args.essai:
        for t, de in [("Rencontre avec l'autrice autour de son dernier roman", "fr"),
                      ("محاضرة حول تاريخ المسرح التونسي", "ar"), ("Live session with local DJs", "en")]:
            print(de, "|", t, "|", {v: traducteur.traduire([t], de, v)[0] for v in LANGUES if v != de})
        return 0
    evts = evenements()
    cache = lire()
    titres, notices = a_faire(evts, cache)
    n = traduire_tout(traducteur, cache, titres, notices) if titres or notices else 0
    nettoyer(cache, evts)
    FICHIER.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n")
    print(f"Traduction : {n} texte(s) traduit(s), {len(cache['titres'])} titres et {len(cache['notices'])} notices en tout")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
