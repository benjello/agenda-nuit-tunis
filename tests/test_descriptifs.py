"""Tests hors ligne des descriptifs : python3 -m unittest tests.test_descriptifs"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scrapers import descriptifs as d

NOTICE = ("Un groupe de jeunes amis se retrouve dans une villa isolée en bord de mer pour un week-end. "
          "Mais la disparition mystérieuse de l'une d'elles va transformer cette escapade en cauchemar.")


class Extraire(unittest.TestCase):
    def test_jsonld(self):
        html = ('<html><head><script type="application/ld+json">{"@type": "TheaterEvent", "name": "Le Fou", '
                f'"description": "<p>{NOTICE}</p>"}}</script></head><body></body></html>')
        self.assertEqual(d.extraire(html, "Le Fou"), NOTICE)

    def test_og_tronquee_remplacee_par_le_texte(self):
        html = (f'<html><head><meta property="og:description" content="{NOTICE[:70]}…"></head>'
                f'<body><nav><p>{"Menu " * 20}</p></nav><article><p>{NOTICE}</p></article></body></html>')
        self.assertEqual(d.extraire(html), NOTICE)

    def test_rien_d_utile(self):
        html = ('<html><head><meta name="description" content="Nous utilisons des cookies pour améliorer votre '
                'expérience sur notre site web."></head><body><p>BAKMA</p></body></html>')
        self.assertEqual(d.extraire(html, "BAKMA"), "")

    def test_titre_seul(self):
        html = '<meta property="og:description" content="BAKMA - Cinéma Le Colisée - BAKMA - Cinéma Le Colisée">'
        self.assertEqual(d.extraire(html, "BAKMA - Cinéma Le Colisée"), "")

    def test_coupe_en_fin_de_phrase(self):
        long = " ".join([NOTICE] * 5)
        t = d.extraire(f'<meta name="description" content="{long}">')
        self.assertLessEqual(len(t), d.LONGUEUR)
        self.assertTrue(t.endswith("."))


class Divers(unittest.TestCase):
    def test_liens_illisibles(self):
        self.assertFalse(d._lisible("https://www.facebook.com/100064660932929/posts/1"))
        self.assertFalse(d._lisible("https://www.instagram.com/p/xyz/"))
        self.assertFalse(d._lisible("https://site.tn/CALENDRIER-11-2026.pdf"))
        self.assertTrue(d._lisible("https://teskerti.tn/evenement/e-fest"))

    def test_slogan_du_site_ecarte(self):
        pages = {"https://a.tn/1": {"texte": "Slogan"}, "https://a.tn/2": {"texte": "Slogan"},
                 "https://b.tn/1": {"texte": "Slogan"}, "https://a.tn/3": {"texte": "Vrai texte"}}
        self.assertEqual(d.textes_generiques(pages), {"Slogan"})


class Ecriture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "teskerti").mkdir()
        self.f = self.tmp / "teskerti" / "2030-01-01-le-fou.md"
        self.f.write_text('---\ntitle: "Le Fou"\ndate: 2030-01-01 20:00\nlink: "https://t.tn/le-fou"\nauto: true\n---\n')
        self.film = self.tmp / "teskerti" / "2030-01-01-weekend.md"
        self.film.write_text('---\ntitle: "Weekend"\ndate: 2030-01-01\nlink: "https://t.tn/weekend"\nfilm: true\n'
                             'auto: true\n---\n')

    def test_notice_de_la_page(self):
        evts = d._evenements(self.tmp)
        cache = {"pages": {"https://t.tn/le-fou": {"texte": NOTICE}}}
        n = d.ecrire_notices(evts, cache, [], {"evenements": {}})
        self.assertEqual(n, 1)
        champs, corps = d._lire(self.f)
        self.assertEqual(champs["title"], "Le Fou")
        self.assertEqual(corps.strip(), NOTICE)
        self.assertNotIn("notice_source", champs)
        # Second passage : la notice est déjà là, rien ne change.
        self.assertEqual(d.ecrire_notices(d._evenements(self.tmp), cache, [], {"evenements": {}}), 0)

    def test_synopsis_d_un_film(self):
        films = [{"id": "weekend", "synopsis": NOTICE, "synopsis_source": "Wikipédia",
                  "salles": [{"lien": "https://t.tn/weekend"}]}]
        d.ecrire_notices(d._evenements(self.tmp), {"pages": {}}, films, {"evenements": {}})
        champs, corps = d._lire(self.film)
        self.assertEqual(champs["notice_source"], "Wikipédia")
        self.assertTrue(champs["auto"])
        self.assertEqual(corps.strip(), NOTICE)

    def test_films_json(self):
        films = self.tmp / "films.json"
        films.write_text(json.dumps([
            {"id": "weekend", "titre": "Weekend", "salles": [{"lien": "https://t.tn/weekend"}]},
            {"id": "inconnu", "titre": "Inconnu", "wikidata": "Q1", "salles": []}]))
        evts = [(self.film, {"title": "Weekend", "film": True, "link": "https://t.tn/weekend"}, NOTICE)]
        cache = {"films": {"inconnu": {"texte": "Résumé Wikipédia du film.", "source": "Wikipédia",
                                       "url": "https://fr.wikipedia.org/wiki/X", "verifie": "2999-01-01"}}}
        with mock.patch.object(d, "FILMS", films):
            res = d.completer_films(cache, d.Budget(0, False), evts, {"films": {}})
        self.assertEqual(res[0]["synopsis"], NOTICE)       # notice d'une salle
        self.assertEqual(res[1]["synopsis_source"], "Wikipédia")


def _entite(label, nature="Q5", pays=None, wiki=True, alias=()):
    claims = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": nature}}}}]}
    if pays:
        claims["P27"] = [{"mainsnak": {"datavalue": {"value": {"id": pays}}}}]
    return {"claims": claims, "labels": {"fr": {"value": label}},
            "aliases": {"fr": [{"value": a} for a in alias]},
            "sitelinks": {"frwiki": {"title": label}} if wiki else {}}


class Personnes(unittest.TestCase):
    def chercher(self, nom, entites):
        def wd(**p):
            if p["action"] == "wbsearchentities":
                return {"search": [{"id": q} for q in entites]}
            return {"entities": entites}
        with mock.patch.object(d, "_wd", wd):
            return d.chercher_personne(nom)

    def test_tunisien_d_abord(self):
        e = {"Q1": _entite("Sami Ben Salah"), "Q2": _entite("Sami Ben Salah", pays="Q948")}
        self.assertEqual(self.chercher("Sami Ben Salah", e), "Q2")

    def test_un_seul_mot(self):
        self.assertIsNone(self.chercher("Amin", {"Q1": _entite("Amin")}))

    def test_nom_different_ou_sans_article_ou_pas_une_personne(self):
        self.assertIsNone(self.chercher("Sami Ben Salah", {"Q1": _entite("Sami Ben Salem")}))
        self.assertIsNone(self.chercher("Sami Ben Salah", {"Q1": _entite("Sami Ben Salah", wiki=False)}))
        self.assertIsNone(self.chercher("Sami Ben Salah", {"Q1": _entite("Sami Ben Salah", nature="Q11424")}))

    def test_alias(self):
        e = {"Q1": _entite("Samuel Ben Salah", alias=["Sami Ben Salah"])}
        self.assertEqual(self.chercher("Sami Ben Salah", e), "Q1")


class Organismes(unittest.TestCase):
    def test_strict(self):
        e = {"claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": "Q948"}}}}]},
             "labels": {"fr": {"value": "Théâtre de l'Opéra"}}, "sitelinks": {"frwiki": {"title": "X"}}}

        def wd(**p):
            return {"search": [{"id": "Q1"}]} if p["action"] == "wbsearchentities" else {"entities": {"Q1": e}}
        with mock.patch.object(d, "_wd", wd):
            self.assertEqual(d.chercher_lieu("Opéra", strict=False), "Q1")
            self.assertIsNone(d.chercher_lieu("Opéra", strict=True))
            self.assertEqual(d.chercher_lieu("Théâtre de l'Opéra", strict=True), "Q1")

    def test_sites(self):
        self.assertEqual(d._nom_court("Beit al-Hikma (Académie tunisienne)"), "Beit al-Hikma")
        self.assertEqual(d._nom_court("La Boîte (Instagram)"), "La Boîte")
        self.assertEqual(d._accueil("https://www.beitalhikma.tn/feed/"), "https://www.beitalhikma.tn/")
        self.assertEqual(d._accueil("https://a.tn/programme/"), "https://a.tn/programme/")
        self.assertEqual(d._site_collectif({"liens": [{"reseau": "facebook", "url": "https://www.facebook.com/x"},
                                                      {"reseau": "site", "url": "https://x.tn/"}]}), "https://x.tn/")
        self.assertEqual(d._site_collectif({"url_source": "https://www.instagram.com/x/"}), "")
        self.assertEqual(d._site_collectif({"url_source": "https://x.tn/feed/"}), "https://x.tn/")

    def test_completer(self):
        """Artiste trouvé sur Wikipédia, collectif sans réseau lisible : cherché une seule fois."""
        tmp = Path(tempfile.mkdtemp())
        (tmp / "_artistes").mkdir()
        (tmp / "_artistes" / "sami-ben-salah.md").write_text('---\ntitle: "Sami Ben Salah"\n---\n')
        (tmp / "_data").mkdir()
        cache = {"recherches": {}}
        appels = []

        def trouver(groupe, el):
            appels.append((groupe, el["nom"]))
            return {"texte": "Musicien.", "source": "Wikipédia", "url": "https://fr.wikipedia.org/wiki/X"} \
                if groupe == "artistes" else None
        vide = {k: {} for k in ("lieux", "festivals", "musees", "artistes", "collectifs")}
        with mock.patch.object(d, "RACINE", tmp), mock.patch.object(d, "_trouver", trouver):
            d.completer_lieux(cache, d.Budget(10, True), vide)
            d.completer_lieux(cache, d.Budget(10, True), vide)
        self.assertEqual(cache["artistes"]["sami-ben-salah"]["texte"], "Musicien.")
        self.assertEqual(appels, [("artistes", "Sami Ben Salah")])  # la seconde passe lit le cache
        d_manuel = {**vide, "artistes": {"sami-ben-salah": "Texte écrit à la main."}}
        with mock.patch.object(d, "RACINE", tmp), mock.patch.object(d, "_trouver", trouver):
            d.completer_lieux(cache, d.Budget(10, True), d_manuel)
        self.assertEqual(cache["artistes"]["sami-ben-salah"], {"texte": "Texte écrit à la main."})


if __name__ == "__main__":
    unittest.main()
