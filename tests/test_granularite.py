"""Granularité : chaque entrée doit être un événement précis (un film, une expo), pas une rubrique.

  python3 -m unittest tests.test_granularite -v

Deux sortes de tests :
- les règles (scrapers/granularite.py, titres de films, titres d'articles…) sur des exemples tirés du site ;
- un garde-fou sur les événements publiés (_events/auto, _data/films.json) : ce que les scrapers et le
  contrôle doivent toujours garantir. Le reste (liens généraux, heures manquantes) n'échoue pas : il est
  compté par source sur la page « Santé des sources ».
"""
import datetime as dt
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

from scrapers import ecriture, granularite
from scrapers.commun import RACINE, Evenement, pas_un_evenement, titre_film, titre_generique
from scrapers.doublons import _lire

FUTUR = dt.date.today().year + 1


class Titres(unittest.TestCase):
    def test_titre_film(self):
        self.assertEqual(titre_film("Movie Night: UN FILS"), "UN FILS")
        self.assertEqual(titre_film("Mercredis-Ciné Level Five"), "Level Five")
        self.assertEqual(titre_film("Ciné-club : Le Kid"), "Le Kid")
        self.assertEqual(titre_film("Cinéma : Le Temps suspendu"), "Le Temps suspendu")
        # le titre du film commence par « Cinéma » : on n'y touche pas
        self.assertEqual(titre_film("Cinéma Paradiso"), "Cinéma Paradiso")
        self.assertEqual(titre_film("Cinéma D’Animation"), "Cinéma D’Animation")
        self.assertEqual(titre_film("BAKMA - بكمة"), "BAKMA - بكمة")

    def test_titre_generique(self):
        for t in ["Exposition", "Tables Rondes", "Cinéma D’Animation", "Diffusion Des Savoirs", "Projection",
                  "Programme du mois", "Concert", "Atelier"]:
            self.assertTrue(titre_generique(t), t)
        for t in ["Le Monde Sans Fin", "Mars Express", "Cosmose", "Becoming The Ocean - BIM'26", "Festival Du Podcast"]:
            self.assertFalse(titre_generique(t), t)

    def test_pas_un_evenement(self):
        self.assertTrue(pas_un_evenement("Dimanche 1er Novembre, la Médiathèque de l'Institut français de Tunisie "
                                         "ouvre exceptionnellement"))
        self.assertTrue(pas_un_evenement("Tunisie | Entrée gratuite aux sites et musées ce 1er novembre"))
        self.assertTrue(pas_un_evenement("Appel à candidatures : résidence d'artistes 2027"))
        self.assertFalse(pas_un_evenement("Ouverture du festival : concert d'Anouar Brahem"))
        self.assertFalse(pas_un_evenement("Le Fou | المجنون"))


class Liens(unittest.TestCase):
    def test_lien_general(self):
        g = granularite.lien_general
        self.assertTrue(g("https://www.institutfrancais-tunisie.com/wp-content/uploads/2026/10/CALENDRIER-11-2026.pdf"))
        self.assertTrue(g("https://www.institutfrancais-tunisie.com/"))
        self.assertTrue(g("https://www.institutfrancais-tunisie.com/list-agenda"))
        self.assertTrue(g("https://tunis.events/cinema"))
        self.assertTrue(g("https://www.facebook.com/IFTunisie"))
        self.assertTrue(g("https://www.instagram.com/cinemadart/"))
        self.assertTrue(g("https://exemple.tn/programme", "https://exemple.tn/programme"))
        self.assertFalse(g("https://lagora.tn/produit/bakma/"))
        self.assertFalse(g("https://tunis.events/fr/cinema/bakma"))
        self.assertFalse(g("https://billetterie.elteatrotunis.com/fr/programme/le_fou"))
        self.assertFalse(g("https://www.facebook.com/100064660932929/posts/1574499701382046"))
        self.assertFalse(g("https://www.instagram.com/p/DfHeBywOLTX/"))
        self.assertFalse(g("https://ra.co/events/2570365"))

    def test_lien_partage(self):
        # 4 films sur une seule affiche Facebook : même lien pour des titres différents
        programme = "https://www.facebook.com/1/posts/2"
        entrees = [{"title": t, "link": programme} for t in ("BAKMA", "WEEKEND", "Dar El 3ers")]
        # un même film dans deux salles garde le même lien : ce n'est pas un défaut
        entrees += [{"title": "Bakma", "link": "https://tunis.events/fr/cinema/bakma"}] * 2
        self.assertEqual(granularite.liens_partages(entrees), {programme})


def _film(**autres):
    c = {"title": "Bakma", "date": f"{FUTUR}-11-01 21:15", "category": "cinema", "film": True,
         "venue": "L'Agora Marsa", "link": "https://lagora.tn/produit/bakma/", "image": "x.jpg"}
    c.update(autres)
    return c


class Defauts(unittest.TestCase):
    def codes(self, champs, corps="Une notice assez longue pour compter comme une vraie notice.", **k):
        return [c for c in granularite.defauts(champs, corps, **k) if c in granularite.DEFAUTS]

    def test_film_precis(self):
        self.assertEqual(self.codes(_film()), [])
        self.assertEqual(self.codes(_film(date=f"{FUTUR}-11-01", seances=[f"{FUTUR}-11-01", f"{FUTUR}-11-02"])), [])

    def test_film_imprecis(self):
        self.assertIn("film_sans_seance", self.codes(_film(date=f"{FUTUR}-11-01")))
        self.assertIn("titre_prefixe", self.codes(_film(title="Movie Night: UN FILS")))
        self.assertIn("titre_generique", self.codes(_film(title="Cinéma D'Animation")))

    def test_expo(self):
        expo = {"title": "Cosmose", "date": f"{FUTUR}-10-30", "end_date": f"{FUTUR}-11-29", "category": "expo",
                "venue": "Agorgi Gallery", "link": "https://www.instagram.com/p/DfHeBywOLTX/"}
        self.assertEqual(self.codes(expo), [])
        sans_fin = dict(expo, end_date=None)
        self.assertEqual(self.codes(sans_fin), ["expo_sans_fin"])
        pdf = dict(expo, title="Exposition", link="https://ift.tn/CALENDRIER-11-2026.pdf")
        self.assertEqual(self.codes(pdf), ["titre_generique", "lien_general"])

    def test_titres_d_annonce(self):
        presse = {"genre": "presse"}
        c = {"title": "Jaou Tunis 2026: Les corps, ces territoires de résistance", "date": f"{FUTUR}-11-22",
             "venue": "Tunisie, voir l'article", "link": "https://www.lapresse.tn/2026/10/31/jaou/"}
        self.assertEqual(self.codes(c, source=presse), ["titre_phrase", "lieu_vague"])
        fb = {"title": "Podcast Days by Tunisia Podcast Festival vous dévoile son programme du 6 et 7 novembre",
              "date": f"{FUTUR}-11-07", "venue": "IFT", "link": "https://www.facebook.com/1/posts/2"}
        self.assertEqual(self.codes(fb), ["titre_phrase"])

    def test_manques(self):
        c = {"title": "Le Fou", "date": f"{FUTUR}-11-07", "category": "theatre", "venue": "El Teatro",
             "link": "https://billetterie.elteatrotunis.com/fr/programme/le_fou"}
        self.assertEqual(granularite.defauts(c, ""), ["sans_heure", "sans_image", "sans_notice"])

    def test_bilan_par_source_et_scraper(self):
        sources = [{"id": "ift-pdf", "scraper": "pdf_programme"}, {"id": "cine-agora", "scraper": "woocommerce_seances"}]
        pdf = "https://ift.tn/CALENDRIER-11-2026.pdf"
        entrees = [({"source": "ift-pdf", "title": t, "date": f"{FUTUR}-11-10 19:00", "category": "expo", "venue": "IFT",
                     "link": pdf}, "") for t in ("Exposition", "Le Monde Sans Fin")]
        entrees += [(dict(_film(), source="cine-agora"), "")]
        b = granularite.bilan(entrees, sources)
        ift = b["sources"]["ift-pdf"]
        self.assertEqual((ift["n"], ift["precis"], ift["pourcent"]), (2, 0, 0))
        self.assertEqual({d["code"]: d["n"] for d in ift["defauts"]},
                         {"titre_generique": 1, "lien_general": 2, "expo_sans_fin": 2})
        self.assertEqual(b["sources"]["cine-agora"]["pourcent"], 100)
        # le pire type de scraper d'abord
        self.assertEqual(list(b["scrapers"]), ["pdf_programme", "woocommerce_seances"])


class Scrapers(unittest.TestCase):
    def test_pdf_ift_titres_precis(self):
        from scrapers.sources.pdf_programme import depuis_texte, titre_precis
        texte = (Path(__file__).parent / "fixtures" / "ift-calendrier.txt").read_text()
        evts = depuis_texte(texte, dt.date(2026, 11, 1), "IFT", "u")
        par_titre = {e.titre: e for e in evts}
        # « TABLES RONDES » : le titre est celui du cycle de débats, pas le genre
        self.assertIn("Entre deux rives", par_titre)
        self.assertEqual(par_titre["Entre deux rives"].categorie, "conference")
        self.assertFalse(any(titre_generique(e.titre) for e in evts))
        # Mars Express (Jérémie Périn, 2023, 1h25) : un film, avec sa séance
        mars = par_titre["Mars Express"]
        self.assertTrue(mars.film)
        self.assertEqual(mars.seances, [dt.datetime(2026, 11, 6, 14, 30)])
        self.assertIn("Jérémie", mars.description)
        self.assertEqual(titre_precis("Exposition", "Explorez l'exposition « Le Monde sans fin », conçue…"),
                         "Le Monde sans fin")
        self.assertEqual(titre_precis("Exposition", "Rien de net ici"), "Exposition")

    def test_presse_titre_evenement(self):
        from scrapers.sources.presse import titre_evenement
        self.assertEqual(titre_evenement("Cinéma : Le Temps suspendu, un film hongrois à ne pas rater"), "Le Temps suspendu")
        self.assertEqual(titre_evenement("« Saveurs et amertume » à la Galerie TGM : Lorsque l’art esquisse les contours"),
                         "Saveurs et amertume")
        self.assertEqual(titre_evenement("Foire nationale du livre tunisien: Traduire, transmettre et penser le savoir"),
                         "Foire nationale du livre tunisien")
        self.assertEqual(titre_evenement("Jaou Tunis 2026: Les corps, ces territoires de résistance"), "Jaou Tunis 2026")

    def test_ecriture_garde_des_evenements_precis(self):
        d = dt.datetime(FUTUR, 11, 5, 19, 0)
        evts = [Evenement(titre="Movie Night: UN FILS", debut=d, lien="https://tunis.events/events/x", categorie="cinema"),
                Evenement(titre="La Médiathèque ouvre exceptionnellement ce dimanche", debut=d, lien="https://fb/1/posts/2"),
                Evenement(titre="Le Fou", debut=d, lien="https://el-teatro/le_fou", categorie="theatre"),
                Evenement(titre="Afro House Night", debut=d, lien="https://tunis.events/events/y", categorie="musique")]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ecriture, "DOSSIER_AUTO", Path(tmp)):
            ecriture.ecrire_evenements({"id": "essai", "nom": "Essai"}, evts)
            titres = sorted(_lire(f)[0]["title"] for f in Path(tmp, "essai").glob("*.md"))
        self.assertEqual(titres, ["Afro House Night"])  # film et pièce : pas des sorties de nuit


class Publies(unittest.TestCase):
    """Garde-fou sur ce qui est en ligne : ce que les scrapers et le contrôle doivent toujours garantir."""

    @classmethod
    def setUpClass(cls):
        cls.entrees = []
        for f in sorted((RACINE / "_events" / "auto").glob("*/*.md")):
            champs, corps = _lire(f)
            if champs and not champs.get("doublon"):
                cls.entrees.append((f, champs))

    def test_pas_d_annonce_de_service(self):
        fautifs = [f.name for f, c in self.entrees if pas_un_evenement(str(c.get("title")))]
        self.assertEqual(fautifs, [])

    def test_films_sous_leur_titre(self):
        fautifs = [f"{f.parent.name}/{f.name} : {c['title']}" for f, c in self.entrees
                   if c.get("film") and (titre_generique(str(c["title"])) or titre_film(str(c["title"])) != c["title"])]
        self.assertEqual(fautifs, [])

    def test_films_avec_un_jour(self):
        fautifs = [f.name for f, c in self.entrees
                   if c.get("film") and not (c.get("seances") or re.match(r"\d{4}-\d{2}-\d{2}", str(c.get("date"))))]
        self.assertEqual(fautifs, [])

    def test_page_cinema(self):
        fichier = RACINE / "_data" / "films.json"
        if not fichier.exists():
            self.skipTest("pas de films.json")
        d = json.loads(fichier.read_text())
        films = d if isinstance(d, list) else d.get("films", [])
        for f in films:
            self.assertFalse(titre_generique(f["titre"]), f["titre"])
            self.assertEqual(titre_film(f["titre"]), f["titre"])
            self.assertTrue(f["salles"], f["titre"])

    def test_bilan_couvre_les_sources(self):
        sources = yaml.safe_load((RACINE / "_data" / "sources.yml").read_text())
        b = granularite.bilan([(c, "") for _, c in self.entrees], sources)
        self.assertEqual(set(b["sources"]), {c.get("source") for _, c in self.entrees})


if __name__ == "__main__":
    unittest.main()


class AgendaEnLigneIFT(unittest.TestCase):
    """API publique de la billetterie AEC (agenda en ligne de l'Institut français) et rapprochement avec le PDF."""

    def setUp(self):
        from scrapers.sources import aec
        objets = json.loads((Path(__file__).parent / "fixtures" / "aec-evenements.json").read_text())
        self.en_ligne = aec.depuis_api(objets, "Institut français de Tunisie")

    def test_api(self):
        par_titre = {e.titre: e for e in self.en_ligne}
        film = par_titre["What else ? (فانا محط بش تتحط ؟)"]
        self.assertEqual((film.categorie, film.film, film.prix, film.lieu), ("cinema", True, "6 DT", "Institut français de Tunis"))
        self.assertEqual(film.lien, "https://www.institutfrancais-tunisie.com/details-agenda/?eventId=6509")
        self.assertTrue(film.image.startswith("https://res.cloudinary.com/aec/"))
        expo = par_titre["Images de Syrie, Palmyre, Alep, Damas"]
        self.assertEqual((expo.categorie, expo.fin), ("expo", dt.datetime(2026, 11, 27)))
        self.assertEqual(par_titre["RUCHE73 : Concert de Yosri"].lieu, "Institut français de Sousse")
        self.assertIn("8e édition", par_titre["Jaou Tunis Biennale - 8e édition"].titre)  # entités HTML décodées
        for e in self.en_ligne:
            self.assertFalse(granularite.lien_general(e.lien), e.lien)

    def test_rapprochement_avec_le_pdf(self):
        from scrapers.sources.pdf_programme import depuis_texte, rapprocher
        pdf_url = "https://www.institutfrancais-tunisie.com/wp-content/uploads/2026/10/CALENDRIER-11-2026.pdf"
        texte = (Path(__file__).parent / "fixtures" / "ift-calendrier.txt").read_text()
        evts = rapprocher(depuis_texte(texte, dt.date(2026, 11, 1), "IFT", pdf_url), self.en_ligne)
        par_jour = {(e.debut.date().isoformat(), e.titre): e for e in evts}
        # « KTEB TOUNSI AVEC ABDELHAMID LARGUÈCHE » (PDF) = « Kteb Tounsi : Rencontre-débat avec … » (en ligne)
        kteb = par_jour[("2026-11-05", "Kteb Tounsi : Rencontre-débat avec Abdelhamid Larguèche")]
        self.assertTrue(kteb.lien.endswith("eventId=6504"))
        self.assertEqual(kteb.lieu, "Médiathèque, Institut français de Tunis")  # la salle du PDF est gardée
        self.assertIn("Kazdaghli", kteb.description)
        # la séance du 1er a sa fiche, celles du 8 et du 22 (absentes du fichier d'essai) gardent le PDF
        biblio = sorted((e.debut.day, e.lien[-4:]) for e in evts if "ibliothérapie" in e.titre)
        self.assertEqual(biblio, [(1, "6505"), (8, ".pdf"), (22, ".pdf")])
        # les événements en ligne absents du PDF sont ajoutés, une seule fois
        self.assertEqual(sum(1 for e in evts if e.lien.endswith("eventId=6509")), 1)
        self.assertEqual(len(evts), len(depuis_texte(texte, dt.date(2026, 11, 1), "IFT", pdf_url)) + 4)
