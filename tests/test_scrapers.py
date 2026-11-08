"""Tests hors ligne des scrapers : python3 -m unittest discover tests

Les pages de tests/fixtures/ imitent la structure des vrais sites. Si un site
change, enregistrer la nouvelle page (python3 -m scrapers --debug) et l'ajouter ici.
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup

from scrapers import commun, ecriture
from scrapers.commun import slug
from scrapers.sources import billetterie_sktech, facebook, facebook_programmes, ical, tunis_events_cinema, jsonld, liste_fiches, pathe, rss, teskerti

FIX = Path(__file__).parent / "fixtures"
FUTUR = dt.date.today().year + 1


def jours(e):
    return [d.date().isoformat() for d in e.seances]


def fixture(nom):
    return (FIX / nom).read_text().replace("{AN}", str(FUTUR))


def faux_reseau(pages):
    def telecharger(url):
        for motif, nom in pages.items():
            if url.rstrip("/").endswith(motif):
                return fixture(nom)
        raise AssertionError(f"page inattendue : {url}")
    return mock.patch.object(commun, "telecharger", telecharger)


class Dates(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(commun.dates_fr("07 Novembre 2026 à 19:30"), [dt.datetime(2026, 11, 7, 19, 30)])
        self.assertEqual(commun.dates_fr("01 Novembre 2026, 11:00"), [dt.datetime(2026, 11, 1, 11, 0)])
        self.assertEqual(commun.dates_fr("le 1er déc. 2026 à 20h"), [dt.datetime(2026, 12, 1, 20, 0)])
        self.assertEqual(commun.dates_fr("5 février 2027"), [dt.datetime(2027, 2, 5)])


class BilletterieSktech(unittest.TestCase):
    def test_el_teatro(self):
        src = {"id": "el-teatro", "nom": "El Teatro", "url": "https://billetterie.elteatrotunis.com/fr/programmes",
               "options": {"lieu": "El Teatro"}}
        with faux_reseau({"/fr/programmes": "sktech-programmes.html", "/fr/programme/le_fou": "sktech-le-fou.html",
                          "/fr/programme/vieux": "sktech-vieux.html"}), mock.patch("time.sleep"):
            evs = billetterie_sktech.recuperer(src)
        self.assertEqual(len(evs), 1)  # le spectacle passé est ignoré
        e = evs[0]
        self.assertEqual(e.titre, "Le Fou | المجنون")
        self.assertEqual(e.debut, dt.datetime(FUTUR, 11, 7, 19, 30))
        self.assertEqual(e.fin, dt.datetime(FUTUR, 11, 14, 19, 30))
        self.assertEqual(len(e.seances), 5)
        self.assertEqual(e.prix, "25 DT")
        self.assertEqual(e.lien, "https://billetterie.elteatrotunis.com/fr/programme/le_fou")


class RetoursLigne(unittest.TestCase):
    def test_rn_redevient_retour_a_la_ligne(self):
        texte = "محمد البركاتيrnMohamed Baraketirnمسرح بيكولو ببنزرتrnThéâtre Piccolo-Bizerte"
        self.assertEqual(commun.retours_ligne_casses(texte),
                         "محمد البركاتي\nMohamed Baraketi\nمسرح بيكولو ببنزرت\nThéâtre Piccolo-Bizerte")
        self.assertEqual(commun.retours_ligne_casses("Une voix...rnUne autre voix"), "Une voix...\nUne autre voix")

    def test_mots_ordinaires_intacts(self):
        for mot in ["journée", "Marne", "carnet", "Cornu", "Ferrand", "CARNAVAL", "arnaque"]:
            self.assertEqual(commun.retours_ligne_casses(mot), mot)


class FicheAvecDateISO(unittest.TestCase):
    """Opéra de Tunis : 0 événement. Les fiches peuvent donner la date en ISO (texte ou <time datetime>)."""

    def test_date_iso_dans_le_texte(self):
        soup = BeautifulSoup(f"<html><body><main><h1>Aida</h1><p>Séance le {FUTUR}-11-07 à 20h00</p></main></body></html>",
                             "html.parser")
        e = liste_fiches.lire_fiche(soup, "https://www.tunisianopera.tn/fr/programme/aida", "Opéra", dt.datetime(2000, 1, 1))
        self.assertIsNotNone(e)
        self.assertEqual(e.titre, "Aida")
        self.assertEqual(e.debut, dt.datetime(FUTUR, 11, 7))

    def test_balise_time(self):
        soup = BeautifulSoup(f'<html><body><h1>Carmen</h1><time datetime="{FUTUR}-12-02T19:30">2 déc.</time>'
                             f'<time datetime="{FUTUR}-12-03T19:30">3 déc.</time></body></html>', "html.parser")
        e = liste_fiches.lire_fiche(soup, "https://www.tunisianopera.tn/fr/programme/carmen", "Opéra", dt.datetime(2000, 1, 1))
        self.assertEqual(e.debut, dt.datetime(FUTUR, 12, 2, 19, 30))
        self.assertEqual(e.fin, dt.datetime(FUTUR, 12, 3, 19, 30))
        self.assertEqual(len(e.seances), 2)


class Teskerti(unittest.TestCase):
    def test_categories_et_fiches(self):
        with faux_reseau({"teskerti.tn": "teskerti-accueil.html", "/category/spectacle": "teskerti-cat-spectacle.html",
                          "/category/cinema": "teskerti-cat-cinema.html",
                          "/evenement/taha-desouky": "teskerti-taha.html",
                          "/evenement/poids-plume-le-rio": "teskerti-poids-plume.html"}), mock.patch("time.sleep"):
            evs = teskerti.recuperer({"id": "teskerti", "nom": "Teskerti", "url": "https://teskerti.tn/"})
        par_titre = {e.titre: e for e in evs}
        self.assertEqual(set(par_titre), {"TAHA DESOUKY", "Poids plume"})  # la catégorie sport est exclue
        t = par_titre["TAHA DESOUKY"]
        self.assertEqual(t.debut, dt.datetime(FUTUR, 11, 5, 20, 0))
        self.assertEqual(t.lieu, "Théâtre municipal de Tunis")
        self.assertEqual(t.adresse, "2 Rue de Grèce, Tunis")
        self.assertEqual(t.categorie, "theatre")  # rubrique spectacle : écartée à l'écriture, sauf titre de soirée
        self.assertEqual(t.prix, "À partir de 30 DT")
        self.assertEqual(par_titre["Poids plume"].categorie, "cinema")
        self.assertEqual(par_titre["Poids plume"].lieu, "Le Rio")


    def test_ignore_les_liens_de_menu(self):
        with faux_reseau({"/evenement/mirage": "teskerti-espace-pro.html"}):
            e = teskerti.lire_fiche("https://teskerti.tn/evenement/mirage", "theatre")
        self.assertEqual(e.titre, "Mirage")
        self.assertEqual((e.lieu, e.adresse), ("Théâtre Le 4ème Art", "7 Av. de Paris"))


    def test_lieu_sous_le_titre(self):
        with faux_reseau({"/evenement/la-chaussure": "teskerti-chaussure.html", "/evenement/e-fest": "teskerti-efest.html"}):
            e = teskerti.lire_fiche("https://teskerti.tn/evenement/la-chaussure", "theatre")
            f = teskerti.lire_fiche("https://teskerti.tn/evenement/e-fest", "autre")
        self.assertEqual((e.lieu, e.adresse), ("Théâtre Le 4ème Art", "7 Av. de Paris"))
        self.assertEqual((f.lieu, f.adresse), ("Carthage Thalasso Resort", "Gammarth"))

    def test_lieu_dans_un_header(self):
        with faux_reseau({"/evenement/fuite": "teskerti-header.html"}):
            e = teskerti.lire_fiche("https://teskerti.tn/evenement/fuite", "theatre")
        self.assertEqual(e.lieu, "Théâtre Le 4ème Art")


class JsonLd(unittest.TestCase):
    def test_evenement_schema_org(self):
        with faux_reseau({"exemple.tn/agenda": "jsonld.html"}):
            evs = jsonld.recuperer({"id": "x", "nom": "X", "url": "https://exemple.tn/agenda"})
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0].titre, "Concert de oud")
        self.assertEqual(evs[0].lieu, "Dar Ben Abdallah")
        self.assertEqual(evs[0].debut, dt.datetime(FUTUR, 12, 3, 20, 0))


class Rss(unittest.TestCase):
    def test_goethe(self):
        evs = rss.depuis_flux(fixture("goethe.rss"), {"id": "goethe", "nom": "Goethe-Institut Tunis", "url": "u",
                                                      "options": {"nettoyer_titre": r"\d{2}\.\d{2}\.\d{4},\s*"}})
        self.assertEqual(len(evs), 2)  # l'actualité sans date est ignorée
        self.assertEqual(evs[0].titre, "Lecture musicale : Rainer Maria Rilke, entre arabe et allemand")
        self.assertEqual(evs[0].debut, dt.datetime(FUTUR, 9, 26, 19, 0))
        self.assertEqual(evs[1].debut, dt.datetime(FUTUR, 9, 27))
        self.assertEqual(evs[0].lien, "https://www.goethe.de/ins/tn/fr/ver.cfm?event_id=27355849")


class Ical(unittest.TestCase):
    def test_ics(self):
        evs = ical.depuis_ics(fixture("agenda.ics"), {"id": "x", "nom": "X", "url": "u"})
        self.assertEqual([(e.titre, e.debut, e.lieu) for e in evs],
                         [("Soirée slam, poésie", dt.datetime(FUTUR, 12, 5, 19, 0), "Café culturel")])


class ListeFiches(unittest.TestCase):
    def test_dates_en_chiffres(self):
        src = {"id": "ift", "nom": "Institut français de Tunisie", "url": "https://www.institutfrancais-tunisie.com/list-agenda",
               "options": {"motif": "details-agenda", "lieu": "Institut français de Tunis"}}
        with faux_reseau({"/list-agenda": "ift-liste.html", "eventId=6509": "ift-fiche.html"}), mock.patch("time.sleep"):
            evs = liste_fiches.recuperer(src)
        self.assertEqual(len(evs), 1)  # deux liens vers la même fiche
        self.assertEqual(evs[0].titre, "What else ?")
        self.assertEqual(evs[0].debut, dt.datetime(FUTUR, 11, 4, 18, 0))
        self.assertEqual(evs[0].lieu, "Institut français de Tunis")


class Pathe(unittest.TestCase):
    def test_api(self):
        today = dt.date(2026, 11, 1)
        seances = {"shows": {"el-sett": {"days": {"2026-11-02": {}, "2026-12-30": {}}}, "vieux": {"days": {"2020-01-01": {}}}}}
        films = pathe.films_depuis_api(seances, {"el-sett": {"title": "El Sett", "duration": 155}}, today)
        self.assertEqual([(f.titre, jours(f), f.duree, f.film, f.categorie) for f in films],
                         [("El Sett", ["2026-11-02"], 155, True, "cinema")])


class Ecriture(unittest.TestCase):
    def test_fichiers_markdown(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ecriture, "DOSSIER_AUTO", Path(d)):
            e = commun.Evenement(titre="L'Effet : papillon", debut=dt.datetime(FUTUR, 11, 7, 19, 30),
                                 fin=dt.datetime(FUTUR, 11, 9, 19, 30), lien="https://x.tn/a", lieu="Lartisto")
            passe = commun.Evenement(titre="Vieux", debut=dt.datetime(2020, 1, 1), lien="https://x.tn/b")
            n = ecriture.ecrire_evenements({"id": "src", "nom": "Source", "categorie": "cabaret"}, [e, passe])
            self.assertEqual(n, 1)
            texte = next(Path(d, "src").glob("*.md")).read_text()
            self.assertIn(f"date: {FUTUR}-11-07 19:30\n", texte)
            self.assertIn('title: "L\'Effet : papillon"', texte)
            self.assertIn('category: "cabaret"', texte)


class RechercheLarge(unittest.TestCase):
    """Recherche Facebook par mots-clés : seules les vraies soirées en Tunisie passent."""

    def test_soiree_sure(self):
        from scrapers.ecriture import soiree_sure
        def ev(titre, heure, lieu):
            return commun.Evenement(titre=titre, debut=dt.datetime(FUTUR, 11, 20, heure, 0), lien="x", lieu=lieu,
                                    categorie=commun.categorie_nuit("autre", titre))
        self.assertTrue(soiree_sure(ev("Afro night DJ set", 23, "Gammarth")))
        self.assertTrue(soiree_sure(ev("Karaoké night", 21, "Le Lac, Tunis")))
        self.assertFalse(soiree_sure(ev("soirée Noël", 0, "Lieu à préciser")))            # titre trop vague
        self.assertFalse(soiree_sure(ev("Soirée Mezwed live", 22, "Montréal")))            # hors Tunisie
        self.assertFalse(soiree_sure(ev("Concert jazz", 11, "Tunis")))                     # le matin
        self.assertEqual(commun.categorie_nuit("autre", "Ateliers de bibliothérapie - Tunis Blues"), "")


class Clubs(unittest.TestCase):
    """Page Clubs & bars : lieux d'OpenStreetMap, horaires en français, corrections de clubs.yml."""

    def test_horaires_et_fusion(self):
        from scrapers import clubs
        self.assertEqual(clubs.horaires_fr("Th-Sa 23:00-05:00; Su off"), "jeu-sam 23h-5h ; dim fermé")
        osm = clubs.depuis_osm([{"type": "node", "id": 1, "lat": 36.40, "lon": 10.61, "tags": {
            "amenity": "nightclub", "name": "Club X", "addr:city": "Hammamet", "opening_hours": "Fr,Sa 23:30-05:00",
            "music:genre": "house;afro", "outdoor_seating": "yes", "contact:instagram": "https://instagram.com/clubx/"}}])
        self.assertEqual((osm[0]["type"], osm[0]["ville"], osm[0]["instagram"]), ("club", "nabeul", "clubx"))
        self.assertEqual(osm[0]["ambiance"], "house, afro, terrasse")
        lieux = clubs.fusionner(osm, [{"nom": "Club X", "gamme": "$$", "dress_code": "chic"},
                                      {"nom": "Bar Y", "type": "bar", "adresse": "La Marsa"}, {"nom": "Fermé", "cacher": True}])
        x = next(l for l in lieux if l["nom"] == "Club X")
        self.assertEqual((x["gamme"], x["horaires"], x["dress_code"]), ("$$", "ven,sam 23h30-5h", "chic"))
        self.assertIn("Bar Y", [l["nom"] for l in lieux])


class FichesClubs(unittest.TestCase):
    def test_instagram_et_site(self):
        from bs4 import BeautifulSoup
        from scrapers import fiches_clubs
        item = {"username": "clubx", "biography": "Jeu-Sam 23h-5h · Résa DM", "followersCount": 1200,
                "externalUrl": "https://clubx.tn", "profilePicUrl": "https://cdn/p.jpg",
                "latestPosts": [{"shortCode": "A1", "displayUrl": "https://cdn/a.jpg", "url": "https://www.instagram.com/p/A1/",
                                 "timestamp": "2026-11-01T20:00:00Z"},
                                {"shortCode": "B2", "displayUrl": "https://cdn/b.jpg", "url": "https://www.instagram.com/p/B2/",
                                 "timestamp": "2026-11-05T20:00:00Z"}]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(fiches_clubs, "DOSSIER", Path(d)), \
                mock.patch.object(fiches_clubs, "enregistrer_image", lambda url, dossier, nom: f"assets/clubs/x/{nom}.jpg"):
            f = fiches_clubs.depuis_instagram(item, "Club X")
        self.assertEqual(f["photo"], "assets/clubs/x/profil.jpg")
        self.assertEqual([a["lien"] for a in f["affiches"]], ["https://www.instagram.com/p/B2/", "https://www.instagram.com/p/A1/"])
        self.assertEqual(f["bio"], "Jeu-Sam 23h-5h · Résa DM")
        html = """<html><head><meta property="og:image" content="https://clubx.tn/x.jpg">
          <script type="application/ld+json">{"@type": "NightClub", "openingHours": ["Th-Sa 23:00-05:00"], "priceRange": "$$"}</script>
          </head></html>"""
        with mock.patch.object(fiches_clubs, "page", lambda url: BeautifulSoup(html, "html.parser")):
            site = fiches_clubs.depuis_site("https://clubx.tn")
        self.assertEqual(site, {"image_site": "https://clubx.tn/x.jpg", "horaires_site": "Th-Sa 23:00-05:00", "prix_site": "$$"})


class Nettoyage(unittest.TestCase):
    """Retour de Mahdi (8 nov. 2026) : des annonces qui ne sont pas des soirées, des cafés dans « Autres »."""

    def test_annonces_hors_nuit(self):
        from scrapers.ecriture import de_jour
        self.assertTrue(commun.pas_un_evenement("2 flight tickets to win, to any destination"))
        self.assertTrue(commun.pas_un_evenement("Jaou Tunis Weekly Guide"))
        def ev(h, cat):
            return commun.Evenement(titre="x", debut=dt.datetime(FUTUR, 12, 20, h, 0), lien="x", categorie=cat)
        self.assertTrue(de_jour(ev(9, "concert")))     # convention du matin
        self.assertFalse(de_jour(ev(12, "soundsystem")))  # midi : heure par défaut d'une affiche
        self.assertFalse(de_jour(ev(14, "festival")))  # day party de festival
        self.assertFalse(de_jour(ev(23, "club")))

    def test_cafes_et_bars_d_hotel(self):
        from scrapers.clubs import hors_sujet
        for nom in ("Go CAfé", "Pool Bar", "Lobby bar", "Salon Des Fêtes Honey Moon", "Tozeur", "Restaurant Sidi Ali"):
            self.assertTrue(hors_sujet(nom), nom)
        for nom in ("Café Bar de la Lyre", "Le Lido", "Novelty Bar", "Calypso Club Hammamet"):
            self.assertFalse(hors_sujet(nom), nom)


class RechercheHashtags(unittest.TestCase):
    def test_classer(self):
        from scrapers.recherche_hashtags import classer
        pubs = [{"ownerUsername": "clubx", "caption": "Ce soir DJ set 🔥 résa en DM", "timestamp": "2026-11-06T20:00:00Z",
                 "url": "https://www.instagram.com/p/1/", "_hashtag": "gammarth"},
                {"ownerUsername": "clubx", "caption": "Saturday night party", "timestamp": "2026-11-07T20:00:00Z",
                 "url": "https://www.instagram.com/p/2/", "_hashtag": "lamarsa"},
                {"ownerUsername": "plage", "caption": "Coucher de soleil", "timestamp": "2026-11-07T18:00:00Z", "_hashtag": "gammarth"},
                {"ownerUsername": "suivi", "caption": "Afro night", "timestamp": "2026-11-05T20:00:00Z", "_hashtag": "gammarth"}]
        c = classer(pubs, {"suivi"})
        self.assertEqual([x["compte"] for x in c], ["clubx", "suivi"])  # la plage n'annonce pas de soirée
        self.assertEqual((c[0]["soirees"], c[0]["derniere"], c[0]["exemple"]), (2, "2026-11-07", "https://www.instagram.com/p/2/"))
        self.assertTrue(c[1]["suivi"])


if __name__ == "__main__":
    unittest.main()


class Lanceur(unittest.TestCase):
    def test_vide_ok_et_panne_garde_les_fichiers(self):
        from scrapers import __main__ as lanceur
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ancien = d / "auto" / "panne"
            ancien.mkdir(parents=True)
            (ancien / "vieux.md").write_text("---\ntitle: x\n---\n")
            sources = [{"id": "vide", "nom": "Vide", "scraper": "x", "actif": True},
                       {"id": "panne", "nom": "Panne", "scraper": "x", "actif": True}]

            def lancer(s):
                if s["id"] == "panne":
                    raise RuntimeError("site modifié")
                return []
            with mock.patch.object(lanceur, "charger_sources", return_value=sources), \
                 mock.patch.object(lanceur, "lancer", lancer), \
                 mock.patch.object(ecriture, "DOSSIER_AUTO", d / "auto"), \
                 mock.patch.object(ecriture, "FICHIER_ETAT", d / "etat.json"), \
                 mock.patch.object(lanceur.doublons, "marquer", return_value=0), \
                 mock.patch.object(lanceur.films, "ecrire", return_value=0), \
                 mock.patch.object(lanceur.controle, "main", return_value=0):
                code = lanceur.main([])
            etat = json.loads((d / "etat.json").read_text())
            self.assertEqual(code, 0)
            self.assertTrue(etat["vide"]["ok"])
            self.assertEqual(etat["vide"]["nb"], 0)
            self.assertFalse(etat["panne"]["ok"])
            self.assertIn("site modifié", etat["panne"]["erreur"])
            self.assertTrue((ancien / "vieux.md").exists())

    def test_attente_et_frequence(self):
        from scrapers import __main__ as lanceur
        hier = (dt.datetime.now() - dt.timedelta(days=1)).isoformat(timespec="seconds")
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "etat.json").write_text(json.dumps({"lent": {"ok": True, "nb": 2, "dernier_succes": hier}}))
            sources = [{"id": "sans-cle", "nom": "A", "scraper": "x"},
                       {"id": "lent", "nom": "B", "scraper": "x", "tous_les_jours": 3}]
            appels = []

            def lancer(s):
                appels.append(s["id"])
                raise commun.EnAttente("clé absente")
            with mock.patch.object(lanceur, "charger_sources", return_value=sources), \
                 mock.patch.object(lanceur, "lancer", lancer), \
                 mock.patch.object(ecriture, "DOSSIER_AUTO", d / "auto"), \
                 mock.patch.object(ecriture, "FICHIER_ETAT", d / "etat.json"), \
                 mock.patch.object(lanceur.doublons, "marquer", return_value=0), \
                 mock.patch.object(lanceur.films, "ecrire", return_value=0), \
                 mock.patch.object(lanceur.controle, "main", return_value=0):
                code = lanceur.main([])
            etat = json.loads((d / "etat.json").read_text())
            self.assertEqual(code, 0)
            self.assertEqual(appels, ["sans-cle"])  # « lent » relu hier : pas relancé
            self.assertEqual(etat["sans-cle"]["attente"], "clé absente")
            self.assertEqual(etat["lent"]["nb"], 2)


class Facebook(unittest.TestCase):
    SOURCE = {"id": "cine-madart", "nom": "CinéMadart (Carthage)", "url": "https://www.facebook.com/CineMadart",
              "scraper": "facebook", "categorie": "cinema", "options": {"page": "CineMadart", "lieu": "CinéMadart"}}

    def test_sans_cle_en_attente(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(commun.EnAttente):
                facebook.recuperer(self.SOURCE)

    def test_conversion(self):
        items = [  # acteur officiel (heure UTC) et autre acteur (heure locale ISO)
            {"name": "Ciné-club : Les Silences du palais", "url": "https://www.facebook.com/events/123/?ref=x",
             "utcStartDate": f"{FUTUR}-11-05T18:30:00.000Z", "location": {"name": "CinéMadart", "streetAddress": "Carthage Dermech"}},
            {"name": "Avant-première", "url": "https://www.facebook.com/events/456/", "startISO": f"{FUTUR}-11-07T20:00:00+01:00"},
            {"name": "Annulé", "url": "https://www.facebook.com/events/789/", "utcStartDate": f"{FUTUR}-11-08T18:00:00Z", "isCanceled": True},
            {"error": "page introuvable"},
        ]
        with mock.patch.dict("os.environ", {"APIFY_TOKEN": "x"}), \
             mock.patch.object(facebook, "appeler_apify", return_value=items) as appel:
            evs = facebook.recuperer(self.SOURCE)
        self.assertEqual(appel.call_args[0][1]["startUrls"], ["https://www.facebook.com/CineMadart/upcoming_hosted_events"])
        self.assertEqual(len(evs), 2)
        self.assertEqual(evs[0].debut, dt.datetime(FUTUR, 11, 5, 19, 30))  # UTC+1 à Tunis
        self.assertEqual(evs[0].lien, "https://www.facebook.com/events/123/")
        self.assertEqual(evs[0].adresse, "Carthage Dermech")
        self.assertEqual(evs[1].debut, dt.datetime(FUTUR, 11, 7, 20, 0))
        self.assertEqual(evs[1].lieu, "CinéMadart")
        self.assertEqual(evs[1].categorie, "cinema")

    def test_url_groupe(self):
        self.assertEqual(facebook.url_evenements("https://www.facebook.com/groups/265611163490450/"),
                         "https://www.facebook.com/groups/265611163490450/events")


class FacebookProgrammes(unittest.TestCase):
    def test_publications_avec_image(self):
        source = {"id": "cine-test", "nom": "Ciné test", "url": "https://www.facebook.com/cinetest",
                  "scraper": "facebook_programmes", "options": {"page": "cinetest", "max": 2}}
        items = [
            {"text": "Sans image", "url": "https://www.facebook.com/p/1", "time": "2026-10-28T10:00:00.000Z"},
            {"text": "Programme du 29/10 au 4/11", "topLevelUrl": "https://www.facebook.com/p/2",
             "time": "2026-10-29T09:00:00.000Z",
             "media": [{"__typename": "Photo", "photo_image": {"uri": "https://scontent.x/a.jpg"},
                        "ocrText": "May be an image of text that says 'MER 29 20H00 FILM A'"}]},
            {"text": "Ancien", "url": "https://www.facebook.com/p/3", "time": "2026-10-20T09:00:00.000Z",
             "media": [{"__typename": "Video", "thumbnail": "https://scontent.x/v.jpg"}]},
        ]
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict("os.environ", {"APIFY_TOKEN": "x"}), \
             mock.patch.object(facebook_programmes, "appeler_apify", return_value=items), \
             mock.patch.object(facebook_programmes, "RACINE", Path(d)), \
             mock.patch.object(facebook_programmes, "DOSSIER_IMAGES", Path(d) / "assets" / "programmes"), \
             mock.patch.object(facebook_programmes, "enregistrer_image",
                               side_effect=lambda url, dossier, nom: f"assets/programmes/cine-test/{nom}.jpg"), \
             mock.patch.object(facebook_programmes, "lire_image", return_value="MER 29 20H00 FILM A"):
            pubs = facebook_programmes.recuperer(source)
        self.assertEqual(len(pubs), 1)  # sans image et vidéo écartées
        self.assertEqual(pubs[0].lien, "https://www.facebook.com/p/2")
        self.assertEqual(pubs[0].date, "2026-10-29")
        self.assertIn("FILM A", pubs[0].ocr_facebook)
        self.assertEqual(pubs[0].ocr, "MER 29 20H00 FILM A")
        self.assertTrue(pubs[0].images[0].startswith("assets/programmes/cine-test/"))


class TunisEventsCinema(unittest.TestCase):
    def test_salles_et_jours(self):
        def ev(nom, lieu, jour, adresse="Tunis"):
            return {"@type": "Event", "name": nom, "startDate": f"{jour}T00:00:00+01:00",
                    "url": f"https://tunis.events/events/x/{slug(nom)}", "image": "https://api.tunis.events/storage/a.jpg",
                    "location": {"@type": "Place", "name": lieu, "address": {"streetAddress": adresse}}}
        objets = [ev("BAKMA", "CinéMadart", f"{FUTUR}-11-01"), ev("BAKMA", "CinéMadart", f"{FUTUR}-11-02"),
                  ev("BAKMA", "Pathé Tunis City", f"{FUTUR}-11-01"), ev("Bakma", "CinéMadart", f"{FUTUR}-11-03"), ev("Weekend", "Pathé Mall of Sousse", f"{FUTUR}-11-01", "Sousse")]
        html = '<script type="application/ld+json">' + json.dumps(objets) + "</script>"
        source = {"id": "tunis-events-cinema", "nom": "tunis.events", "url": "https://tunis.events/cinema"}
        with mock.patch.object(commun, "telecharger", return_value=html):
            films = tunis_events_cinema.recuperer(source)
        par_salle = {(f.lieu, f.titre): f for f in films}
        self.assertEqual(set(par_salle), {("CinéMadart", "BAKMA"), ("Pathé Tunis City", "BAKMA")})  # Sousse écarté
        madart = par_salle[("CinéMadart", "BAKMA")]  # « Bakma » fusionné avec « BAKMA »
        self.assertEqual(jours(madart), [f"{FUTUR}-11-01", f"{FUTUR}-11-02", f"{FUTUR}-11-03"])
        self.assertTrue(madart.film)
        self.assertEqual(madart.image, "https://api.tunis.events/storage/a.jpg")


class Lecteurs(unittest.TestCase):
    def setUp(self):
        from scrapers import lecteurs
        self.l = lecteurs

    def test_liste_films(self):
        texte = (f"À l'affiche du 02 au 09 Novembre {FUTUR} dans votre Cinéma Alhambra :\n\n"
                 "🎬 𝗪𝗲𝗲𝗸𝗲𝗻𝗱\n🎬 𝗗𝗮𝗿 𝗘𝗹 𝟯𝗲𝗿𝘀 دار العرس\n🎫 Les tickets sont disponibles")
        films = self.l.liste_films([{"texte": texte, "lien": "https://fb/p/1"}], ["Dar El 3ers - دار العرس"])
        self.assertEqual([f.titre for f in films], ["Weekend", "Dar El 3ers - دار العرس"])
        self.assertEqual(len(films[0].seances), 8)
        self.assertEqual(jours(films[0])[0], f"{FUTUR}-11-02")
        self.assertEqual(films[0].lieu, "")

    def test_un_film_par_affiche(self):
        pubs = [
            {"texte": "Rappel Japan Festival", "lien": "https://fb/p/2", "date": f"{FUTUR}-10-28",
             "ocr": "Le Maître du kabuki\nUn film de Lee Sang-il\nVendredi 30 octobre à 19h\n'et dimanche ler novembre à 13h"},
            {"texte": 'تذكير فيلم "بكْمَة" بقاعة Ciné 350', "lien": "https://fb/p/3", "date": f"{FUTUR}-10-28",
             "ocr": "Mercredi 29 Octobre\nJeudi 30 Octobre 16H00"},
        ]
        films = self.l.un_film_par_affiche(pubs, ["BAKMA - بكمة"])
        self.assertEqual(films[0].titre, "Le Maître du kabuki")
        self.assertEqual(jours(films[0]), [f"{FUTUR}-10-30", f"{FUTUR}-11-01"])
        self.assertEqual(films[1].titre, "BAKMA - بكمة")  # rapproché du titre connu, malgré les voyelles

    def test_annee_deduite(self):
        self.assertEqual(self.l.jours_sans_annee("samedi 3 janvier", dt.date(2026, 12, 20)), ["2027-01-03"])


class Doublons(unittest.TestCase):
    def test_meme_lieu_meme_heure(self):
        from scrapers import doublons
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for src, nom, lieu, titre in [("el-teatro", "El Teatro", "El Teatro", "هروب|FUITE"),
                                          ("teskerti", "Teskerti", "El Teatro التياترو", "Fuite"),
                                          ("teskerti", "Teskerti", "Théâtre Le 4ème Art", "Cloche")]:
                (d / src).mkdir(exist_ok=True)
                (d / src / f"{slug(titre)}.md").write_text(
                    f'---\ntitle: "{titre}"\ndate: {FUTUR}-11-02 17:00\nvenue: "{lieu}"\n'
                    f'link: "https://{src}.tn/{slug(titre)}"\nsource: "{src}"\nsource_name: "{nom}"\nauto: true\n---\n')
            sources = [{"id": "el-teatro", "type": "lieu"}, {"id": "teskerti", "type": "billetterie"}]
            self.assertEqual(doublons.marquer(sources, d), 1)
            self.assertIn("doublon: true", (d / "teskerti" / "fuite.md").read_text())
            garde = (d / "el-teatro" / f"{slug('هروب|FUITE')}.md").read_text()
            self.assertIn('"name": "Teskerti"', garde)
            self.assertIn(f"date: {FUTUR}-11-02 17:00\n", garde)
            self.assertNotIn("doublon", (d / "teskerti" / "cloche.md").read_text())
            # relancer ne change rien
            self.assertEqual(doublons.marquer(sources, d), 1)


    def test_meme_jour_titres_proches(self):
        from scrapers import doublons
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for src, lieu, titre, heure in [("ift-pdf", "Institut français de Tunis", "Festival Du Podcast", "10:00"),
                                            ("fb-ift", "L'institut Français de Tunisie", "Podcast Days by Tunisia Podcast Festival", "11:00"),
                                            ("fb-ift", "L'institut Français de Tunisie", "Concert de jazz", "20:00"),
                                            ("presse", "Tunisie, voir l'article", "Concert de jazz Manouche Trio", "00:00"),
                                            ("autre", "L'Agora", "Jazz Manouche Trio", "20:00")]:
                (d / src).mkdir(exist_ok=True)
                (d / src / f"{slug(titre)}.md").write_text(
                    f'---\ntitle: "{titre}"\ndate: {FUTUR}-11-07 {heure}\nvenue: "{lieu}"\n'
                    f'link: "https://{src}.tn/x"\nsource: "{src}"\nsource_name: "{src}"\nauto: true\n---\n')
            sources = [{"id": "ift-pdf", "type": "lieu"}, {"id": "fb-ift", "type": "agenda"},
                       {"id": "presse", "type": "agenda"}, {"id": "autre", "type": "lieu"}]
            self.assertEqual(doublons.marquer(sources, d), 2)
            self.assertIn("doublon: true", (d / "fb-ift" / "podcast-days-by-tunisia-podcast-festival.md").read_text())
            self.assertIn("doublon: true", (d / "presse" / "concert-de-jazz-manouche-trio.md").read_text())
            self.assertNotIn("doublon", (d / "fb-ift" / "concert-de-jazz.md").read_text())
            self.assertNotIn("doublon", (d / "autre" / "jazz-manouche-trio.md").read_text())


    def test_lieu_a_preciser_ne_bloque_pas_le_rapprochement(self):
        """Même titre le même jour : « Lieu à préciser » est un lieu inconnu, pas un autre lieu."""
        from scrapers import doublons
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for src, lieu in [("ig-x", "L'Art Rue"), ("fb-x", "Lieu à préciser")]:
                (d / src).mkdir()
                (d / src / "a.md").write_text(
                    f'---\ntitle: "Le podcast de demain, vous l\'imaginez comment ?"\ndate: {FUTUR}-11-07\nvenue: "{lieu}"\n'
                    f'link: "https://{src}.tn/x"\nsource: "{src}"\nsource_name: "{src}"\nauto: true\n---\n')
            sources = [{"id": "ig-x", "type": "agenda"}, {"id": "fb-x", "type": "agenda"}]
            self.assertEqual(doublons.marquer(sources, d), 1)

    def test_article_au_titre_generique_cite_le_titre_de_l_expo(self):
        """« À l'Institut français de Tunis » ne ressemble pas au titre de l'expo, mais son texte la cite."""
        from scrapers import doublons
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for src, titre, debut, corps in [
                ("ift-pdf", "Images de Syrie, Palmyre, Alep, Damas", f"{FUTUR}-10-27 18:00", ""),
                ("presse-x", "À l’Institut français de Tunis", f"{FUTUR}-10-27",
                 "L'Institut accueille l'exposition « Images de Syrie, Palmyre, Alep, Damas ».")]:
                (d / src).mkdir()
                (d / src / f"{slug(titre)}.md").write_text(
                    f'---\ntitle: "{titre}"\ndate: {debut}\nend_date: "{FUTUR}-11-27"\nvenue: "Institut français de Tunis"\n'
                    f'link: "https://{src}.tn/x"\nsource: "{src}"\nsource_name: "Journal"\nauto: true\n---\n{corps}\n')
            sources = [{"id": "ift-pdf", "type": "lieu"}, {"id": "presse-x", "type": "agenda", "genre": "presse"}]
            self.assertEqual(doublons.marquer(sources, d), 1)
            self.assertNotIn("doublon", (d / "ift-pdf" / "images-de-syrie-palmyre-alep-damas.md").read_text())
            self.assertIn("doublon: true", (d / "presse-x" / f"{slug('À l’Institut français de Tunis')}.md").read_text())

    def test_article_de_presse_recoupe_une_expo_officielle(self):
        """Expo du 27 oct. au 27 nov. : l'article de presse (paru plus tard, même lieu) devient un lien « presse »."""
        from scrapers import doublons
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for src, titre, debut, extra in [
                ("ift-pdf", "Images de Syrie, Palmyre, Alep, Damas", f"{FUTUR}-10-27 18:00", ""),
                ("presse-x", "Images de Syrie : Palmyre, Alep, Damas", f"{FUTUR}-10-31",
                 'article_titre: "À l’Institut français de Tunis : la Syrie regardée"\n')]:
                (d / src).mkdir()
                (d / src / f"{slug(titre)}.md").write_text(
                    f'---\ntitle: "{titre}"\ndate: {debut}\nend_date: "{FUTUR}-11-27"\nvenue: "Institut français de Tunis"\n'
                    f'link: "https://{src}.tn/x"\nsource: "{src}"\nsource_name: "Journal"\n{extra}auto: true\n---\n')
            sources = [{"id": "ift-pdf", "type": "lieu"}, {"id": "presse-x", "type": "agenda", "genre": "presse"}]
            self.assertEqual(doublons.marquer(sources, d), 1)
            officiel = (d / "ift-pdf" / "images-de-syrie-palmyre-alep-damas.md").read_text()
            self.assertNotIn("doublon", officiel)
            self.assertIn("presse:", officiel)
            self.assertIn("la Syrie regardée", officiel)
            self.assertNotIn("autres_sources", officiel)
            self.assertIn("doublon: true", (d / "presse-x" / "images-de-syrie-palmyre-alep-damas.md").read_text())


    def test_article_sans_evenement_rattache_a_la_manifestation(self):
        from scrapers import doublons
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ift").mkdir()
            (d / "ift" / "jaou.md").write_text(
                f'---\ntitle: "Jaou Tunis biennale 8e édition"\ndate: {FUTUR}-10-23\nend_date: "{FUTUR}-11-22"\n'
                f'venue: "Institut français de Tunis"\nlink: "https://ift.tn/x"\nsource: "ift"\nsource_name: "IFT"\nauto: true\n---\n')
            art = [{"titre": "Jaou Tunis 2026 : les corps", "evenement": "Jaou Tunis 2026", "lien": "https://lp/j",
                    "source_nom": "La Presse", "date": f"{FUTUR}-10-31", "debut": f"{FUTUR}-11-22", "fin": f"{FUTUR}-11-22", "lieu": ""},
                   {"titre": "Autre sujet", "evenement": "Autre sujet", "lien": "https://lp/k", "source_nom": "La Presse",
                    "date": f"{FUTUR}-10-31", "debut": f"{FUTUR}-11-22", "fin": f"{FUTUR}-11-22", "lieu": ""}]
            doublons.marquer([{"id": "ift", "type": "lieu"}], d, art)
            texte = (d / "ift" / "jaou.md").read_text()
            self.assertIn("https://lp/j", texte)
            self.assertNotIn("https://lp/k", texte)


class AgendaDuJour(unittest.TestCase):
    def test_blocs_heure_ville(self):
        from scrapers.sources.agenda_du_jour import evenements
        contenu = ("<h3>16h00 — Ben Guerdane</h3><p><strong>37e Festival international d’équitation</strong></p>"
                   "<p>📍 Hippodrome Marsa El Ksiba</p><ul><li>Course nationale</li></ul>"
                   "<h3>19h00 — Carthage</h3><p><strong>Musée national de Carthage</strong></p>"
                   "<ul><li>Spectacle « 100 violons » de <strong>Zied Zouari</strong></li></ul>"
                   "<h3>10h00 — Bardo</h3><p><strong>Assemblée des représentants du peuple</strong></p>"
                   "<ul><li>Séance plénière consacrée au budget de la culture</li></ul>")
        evts = evenements({"titre": "Agenda du samedi 25 juillet 2026 : les principaux rendez-vous", "lien": "x"}, contenu)
        self.assertEqual([(e.debut.hour, e.titre, e.lieu) for e in evts], [
            (16, "37e Festival international d’équitation", "Hippodrome Marsa El Ksiba, Ben Guerdane"),
            (19, "Spectacle « 100 violons » de Zied Zouari", "Musée national de Carthage")])
        from scrapers.villes import ville
        self.assertEqual(ville(evts[0].lieu), "sud")


class Festivals(unittest.TestCase):
    def test_dates_confirmees_seulement(self):
        import datetime as dt
        from scrapers import festivals
        fs = [{"id": "a", "nom": "Festival A", "debut": dt.date(2026, 12, 19), "fin": dt.date(2026, 12, 22), "lieu": "Douz", "ville": "sud"},
              {"id": "b", "nom": "Festival B", "periode": "Été"},
              {"id": "c", "nom": "Médina", "debut": dt.date(2027, 2, 10), "date_estimee": True},
              {"id": "d", "nom": "Vieux", "debut": dt.date(2026, 1, 1)},
              {"id": "e", "nom": "Fabrika Festival", "debut": dt.date(2026, 11, 5), "mots": "Fabrika"}]
        gardes = festivals.a_ecrire(fs, ["Fabrika Festival 14"], dt.date(2026, 11, 1))
        self.assertEqual([f["id"] for f in gardes], ["a"])
        nom, texte = festivals.fichier(gardes[0])
        self.assertEqual(nom, "2026-12-19-a.md")
        self.assertIn('end_date: "2026-12-22"', texte)
        self.assertIn('ville: "sud"', texte)


class Bilan(unittest.TestCase):
    def test_compte_par_ville_et_source(self):
        import datetime as dt
        from scrapers import bilan
        auj = dt.date(2026, 11, 1)
        evts = [{"date": "2026-11-02 20:00", "source": "a", "ville": "sfax", "category": "musique"},
                {"date": "2026-11-03", "source": "b", "ville": "tunis", "film": True, "title": "F"},
                {"date": "2026-11-03", "source": "c", "ville": "tunis", "film": True, "title": "F"},
                {"date": "2026-10-20", "end_date": "2026-11-20", "source": "a", "ville": "sfax", "category": "expo"},
                {"date": "2026-12-20", "source": "a", "ville": "sfax"},
                {"date": "2026-10-01", "source": "a"}]
        sources = [{"id": "a", "genre": "lieu"}, {"id": "b", "genre": "agenda"}, {"id": "c"}, {"id": "d"}]
        b = bilan.compter(evts, auj, sources)
        self.assertEqual((b["sept_jours"], b["a_venir"]), (3, 4))
        self.assertEqual(b["par_ville"], {"sfax": 2, "tunis": 1})
        self.assertEqual(b["sources_muettes"], ["c", "d"])
        self.assertEqual(b["semaine"], "2026-S44")


class Traduction(unittest.TestCase):
    def test_langue_et_choix(self):
        from scrapers import traduire
        self.assertEqual(traduire.langue("محاضرة حول المسرح"), "ar")
        self.assertEqual(traduire.langue("Live session with local DJs"), "en")
        self.assertEqual(traduire.langue("Rencontre avec l'autrice"), "fr")
        self.assertFalse(traduire.a_traduire("Hyperculte"))
        self.assertFalse(traduire.a_traduire("هروب|FUITE"))
        self.assertTrue(traduire.a_traduire("Rencontre avec Sonia Hanihina"))

    def test_cache_et_pivot(self):
        from scrapers import traduire
        class Faux(traduire.Traducteur):
            def __init__(self):
                self.appels = []
            def _direct(self, phrases, de, vers):
                self.appels.append((de, vers))
                return [f"{vers}:{p}" for p in phrases]
        t = Faux()
        self.assertEqual(t.traduire(["Bonjour. Au revoir."], "fr", "ar"), ["ar:en:Bonjour. ar:en:Au revoir."])
        self.assertEqual(t.appels, [("fr", "en"), ("en", "ar")])
        cache = {"titres": {"Déjà traduit ici": {"en": "x"}}, "notices": {}}
        evts = [("_events/a.md", {"title": "Déjà traduit ici"}, ""), ("_events/b.md", {"title": "Concert de jazz"}, "")]
        titres, notices = traduire.a_faire(evts, cache)
        self.assertEqual((titres, notices), (["Concert de jazz"], []))


class Films(unittest.TestCase):
    def test_regroupe_les_salles_par_film(self):
        from scrapers import films
        demain = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        hier = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            def ecrit(src, nom, titre, salle, jours, image=""):
                (d / src).mkdir(exist_ok=True)
                seances = "\n".join(f"  - {j}" for j in jours)
                (d / src / nom).write_text(f'---\ntitle: "{titre}"\ndate: {jours[0]}\nvenue: "{salle}"\n'
                                           f'seances:\n{seances}\nimage: "{image}"\nfilm: true\nsource: "{src}"\n---\n')
            ecrit("a", "1.md", "LAST CHANCE - لص شايح", "Le Palace", [demain], "x.jpg")
            ecrit("b", "2.md", "لص شايح", "Alhambra", [hier, demain])
            ecrit("b", "3.md", "Weekend", "Alhambra", [demain])
            ecrit("a", "4.md", "WEEKEND", "Le Palace", [demain])
            ecrit("a", "5.md", "Vieux film", "Le Palace", [hier])
            fs = films.regrouper(d)
        self.assertEqual(len(fs), 2)
        lc = next(f for f in fs if "LAST" in f["titre"])
        self.assertEqual(lc["titre"], "LAST CHANCE - لص شايح")
        self.assertEqual(lc["image"], "x.jpg")
        self.assertEqual([s["nom"] for s in lc["salles"]], ["Alhambra", "Le Palace"])
        self.assertEqual(lc["salles"][0]["jours"], [demain])  # jour passé retiré
        self.assertEqual([Path(c).name for c in lc["fichiers"]], ["1.md", "2.md"])  # pour l'encadré presse

    def test_horaires_par_jour(self):
        from scrapers import films
        demain = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a").mkdir()
            (d / "a" / "1.md").write_text(f'---\ntitle: "Bakma"\ndate: "{demain} 13:45"\nvenue: "Le Palace"\n'
                                          f'seances:\n  - "{demain} 13:45"\n  - "{demain} 19:45"\nfilm: true\nsource: "a"\n---\n')
            fs = films.regrouper(d)
        self.assertEqual(fs[0]["salles"][0]["heures"], [{"jour": demain, "heures": ["13:45", "19:45"]}])


class Critiques(unittest.TestCase):
    def test_articles_de_film_du_flux(self):
        from scrapers.sources import presse
        xml = ('<?xml version="1.0"?><rss><channel>'
               '<item><title>Cinéma : Le Temps suspendu, un film hongrois à ne pas rater</title><link>https://w/1</link>'
               '<pubDate>Sun, 01 Nov 2026 10:00:00 +0100</pubDate><description>Critique</description></item>'
               '<item><title>Le ministre inaugure une route</title><link>https://w/2</link></item>'
               '</channel></rss>')
        arts = presse.articles_de_film(xml, {"id": "presse-webdo", "nom": "Webdo"})
        self.assertEqual(len(arts), 1)
        self.assertEqual(arts[0]["film"], "Le Temps suspendu")
        self.assertEqual((arts[0]["source_nom"], arts[0]["date"]), ("Webdo", "2026-11-01"))
        self.assertEqual(presse.depuis_flux(xml, {"url": "u", "categorie": "autre"}), [])  # pas un événement

    def test_rattache_les_articles_au_bon_film(self):
        from scrapers.critiques import parle_du_film, rattacher
        a = lambda titre, film="": {"titre": titre, "film": film, "lien": titre, "source_nom": "Webdo", "date": "2026-11-01"}  # noqa: E731
        self.assertTrue(parle_du_film(a("Cinéma : Bakma, une comédie tunisienne", "Bakma"), "BAKMA - بكمة"))
        self.assertTrue(parle_du_film(a("Pourquoi il faut voir Last Chance en salles"), "LAST CHANCE - لص شايح"))
        self.assertTrue(parle_du_film(a("Le film « Weekend » cartonne"), "WEEKEND"))
        self.assertFalse(parle_du_film(a("Un weekend de cinéma à Carthage"), "WEEKEND"))  # un seul mot, sans guillemets
        self.assertFalse(parle_du_film(a("Cinéma : Nahla, premier film de…", "Nahla"), "BAKMA - بكمة"))
        films = [{"titre": "BAKMA - بكمة"}, {"titre": "Autre film"}]
        rattacher(films, [a("Cinéma : Bakma, une comédie", "Bakma")])
        self.assertEqual([x["titre"] for x in films[0]["presse"]], ["Cinéma : Bakma, une comédie"])
        self.assertEqual(films[1]["presse"], [])

    def test_garder_accumule_et_oublie_les_vieux(self):
        from scrapers import critiques
        vieux = (dt.date.today() - dt.timedelta(days=critiques.JOURS_GARDES + 5)).isoformat()
        aujourd_hui = dt.date.today().isoformat()
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "critiques.json"
            critiques.garder([{"lien": "a", "date": vieux}, {"lien": "b", "date": aujourd_hui}], f)
            n = critiques.garder([{"lien": "c", "date": aujourd_hui}], f)
            self.assertEqual(n, 2)
            self.assertEqual(sorted(x["lien"] for x in critiques.lire(f)), ["b", "c"])


class Conferences(unittest.TestCase):
    def sources(self):
        import yaml
        return {s["id"]: s for s in yaml.safe_load((commun.RACINE / "_data" / "sources.yml").read_text())}

class Wikidata(unittest.TestCase):
    def test_fiche_film(self):
        from scrapers import wikidata
        an = dt.date.today().year

        def snak(v):
            return {"mainsnak": {"datavalue": {"value": v}}}
        film = {"claims": {"P345": [snak("tt1234567")], "P6127": [snak("bakma")], "P577": [snak({"time": f"+{an}-05-01T00:00:00Z"})],
                           "P136": [snak({"id": "Q1"}), snak({"id": "Q2"})], "P495": [snak({"id": "Q948"})],
                           "P2758": [snak({"id": "Q3"})]},
                "labels": {"fr": {"value": "Bakma"}}}
        vieux = {"claims": {"P345": [snak("tt0000001")], "P577": [snak({"time": "+1990-01-01T00:00:00Z"})]}}
        libelles = {"Q1": "film dramatique", "Q2": "thriller", "Q3": "interdit aux moins de 12 ans"}

        def api(**p):
            if p["action"] == "wbsearchentities":
                return {"search": [{"id": "Q10"}, {"id": "Q11"}, {"id": "Q12"}]}
            ids = p["ids"].split("|")
            base = {"Q10": film, "Q11": vieux, "Q12": {"claims": {}}}
            return {"entities": {i: base.get(i) or {"labels": {"fr": {"value": libelles[i]}}} for i in ids}}
        with mock.patch.object(wikidata, "_api", api):
            t = wikidata.chercher(["bakma"], an - 3)
            f = wikidata.fiche(t["qid"], t["entite"])
        self.assertEqual(f["qid"], "Q10")
        self.assertEqual(f["imdb"], "tt1234567")
        self.assertEqual(f["letterboxd"], "bakma")
        self.assertEqual(f["genres"], ["Drame", "Thriller"])
        self.assertEqual(f["age"], "-12")
        self.assertTrue(f["tunisien"])

class ProgrammePdf(unittest.TestCase):
    def test_dates_sur_plusieurs_jours_et_non_culturel(self):
        from scrapers.sources.pdf_programme import categorie_ift, depuis_texte, titre_francais, _NON_CULTUREL
        texte = ("INSTITUT FRANÇAIS DE TUNIS\n\n"
                 "EXPOSITION D'ART                                          12\n"
                 "Des oeuvres de plusieurs artistes.                         EXPOSITION\n"
                 "                                                          >> 15\n"
                 "                                                          Galerie\n")
        evts = depuis_texte(texte, dt.date(2026, 11, 1), "IFT", "u")
        for e in evts:
            self.assertEqual((e.debut.day, e.fin.day if e.fin else None), (12, 15))
        self.assertEqual(titre_francais("L'HEURE DU JEU"), "L’Heure du Jeu")
        self.assertEqual(categorie_ift("Café Philo avec Azza Filali", "", "autre"), "conference")
        self.assertEqual(categorie_ift("Contes en scène", "", "autre"), "spectacle")
        self.assertTrue(_NON_CULTUREL.search("Action de sensibilisation et de prévention du diabète"))


class Prix(unittest.TestCase):
    def test_prix_du_texte(self):
        from scrapers.commun import prix_du_texte
        self.assertEqual(prix_du_texte("COVER 10DT, starting from 18:00"), "10 DT")
        self.assertEqual(prix_du_texte("Entrée libre dans la limite des places"), "Gratuit")
        self.assertEqual(prix_du_texte("Billets : 20 DT et 35 DT"), "20 à 35 DT")
        self.assertEqual(prix_du_texte("Prix de 1500 DT pour le lauréat"), "")


class Villes(unittest.TestCase):
    def test_ville(self):
        from scrapers.villes import ville
        self.assertEqual(ville("Institut français de Sousse"), "sousse")
        self.assertEqual(ville("One Resort, Monastir"), "monastir")
        self.assertEqual(ville("L'Agora Marsa", "5 avenue Taïeb Mhiri, La Marsa"), "tunis")
        self.assertEqual(ville("Théâtre", "Houmt Souk, Djerba"), "sud")


class PresseDatesTitres(unittest.TestCase):
    def test_dates_collees_et_abregees(self):
        from scrapers.sources import presse
        self.assertEqual(presse.recoller("expo jusqu'au27nov. à Tunis"), "expo jusqu'au 27 nov. à Tunis")
        self.assertEqual(presse.recoller("du27 octobre au3 novembre"), "du 27 octobre au 3 novembre")
        ref = dt.date(2026, 10, 31)
        self.assertEqual(presse.periode_abregee("du 27 oct. au 27 nov.", ref), (dt.date(2026, 10, 27), dt.date(2026, 11, 27)))
        self.assertEqual(presse.periode_abregee("jusqu'au 27 novembre", ref)[1], dt.date(2026, 11, 27))

    def test_titre_lieu_remplace_par_le_nom_cite(self):
        from scrapers.sources.presse import titre_evenement
        texte = "L'Institut français accueille l'exposition « Images de Syrie : Palmyre, Alep, Damas » du photographe."
        self.assertEqual(titre_evenement("À l’Institut français de Tunis : La Syrie regardée sans indifférence", texte),
                         "Images de Syrie : Palmyre, Alep, Damas")
        self.assertEqual(titre_evenement("À l’Institut français de Tunis : La Syrie regardée", ""), "La Syrie regardée")

    def test_categorie_depuis_le_texte(self):
        from scrapers.sources import presse
        xml = ('<?xml version="1.0"?><rss><channel><item><title>À l’Institut français de Tunis : La Syrie regardée</title>'
               '<link>https://x/1</link><description>L\'Institut français accueille l\'exposition « Images de Syrie » '
               'jusqu\'au27 décembre.</description></item></channel></rss>')
        e = presse.depuis_flux(xml, {"url": "u", "categorie": "autre"})[0]
        self.assertEqual((e.titre, e.categorie), ("Images de Syrie", "expo"))
        self.assertEqual(e.article, "À l’Institut français de Tunis : La Syrie regardée")


    def test_nouvelle_au_passe_jamais_un_evenement(self):
        """« Le Prix Saint Augustin distingue l'historien… » (Kapitalis) : une nouvelle, pas un événement."""
        from scrapers.sources import presse
        d = dt.date.today() + dt.timedelta(days=10)
        mois = list(commun.MOIS)[[v for v in commun.MOIS.values()].index(d.month)]
        xml = (f'<?xml version="1.0"?><rss><channel><item><title>Le Prix Saint Augustin distingue l’historien Abdelhamid Larguèche</title>'
               f'<link>https://x/1</link><description>L’historien et écrivain a été distingué par le Prix Saint Augustin, '
               f'remis le {d.day} {mois} {d.year}.</description></item></channel></rss>')
        for genre in ("presse", "administration"):
            evts, articles = presse.analyser(xml, {"id": "k", "nom": "Kapitalis", "url": "u", "genre": genre})
            self.assertEqual((evts, articles), ([], []))
        self.assertTrue(presse._NOUVELLE.search("Il a été distingué par un prix"))
        self.assertFalse(presse._NOUVELLE.search("Le festival a été inauguré vendredi soir"))

    def test_festival_sans_lieu_devient_une_entree_festival(self):
        from scrapers.sources import presse
        d = dt.date.today() + dt.timedelta(days=10)
        mois = list(commun.MOIS)[[v for v in commun.MOIS.values()].index(d.month)]
        xml = (f'<?xml version="1.0"?><rss><channel><item><title>Ouverture des « Saisons de la création » : un théâtre en mouvement</title>'
               f'<link>https://x/1</link><description>Le festival se tient jusqu\'au {d.day} {mois} {d.year}.</description></item></channel></rss>')
        evts, articles = presse.analyser(xml, {"id": "j", "nom": "Journal", "url": "u", "genre": "presse", "categorie": "autre"})
        self.assertEqual(articles, [])
        self.assertEqual((evts[0].titre, evts[0].festival), ("Saisons de la création", "saisons-de-la-creation"))
        self.assertNotEqual(evts[0].categorie, "autre")


class TunisEvents(unittest.TestCase):
    def test_details_page(self):
        from scrapers.commun import details_page
        d = details_page("📍 Lieu : Université de La Manouba et Amphithéâtre Carthage Al Hadatha\n📅 Dates : 3–5 décembre 2026")
        self.assertEqual(d["lieu"], "Université de La Manouba et Amphithéâtre Carthage Al Hadatha")
        self.assertEqual((d["debut"].day, d["fin"].day, d["fin"].month), (3, 5, 12))

    def test_discret(self):
        from scrapers.commun import est_discret
        self.assertTrue(est_discret("Power Yoga with Nicole"))
        self.assertFalse(est_discret("Labes - Selim Ben Safia"))

    def test_categorie_du_titre(self):
        from scrapers.commun import categorie_du_titre
        self.assertEqual(categorie_du_titre("Movie Night: UN FILS"), "")
        self.assertEqual(categorie_du_titre("Listening Session, Screening & Live Performance"), "concert")
        self.assertEqual(categorie_du_titre("Secret Vibes : DJ set all night long"), "club")
        self.assertEqual(categorie_du_titre("Soirée karaoké du jeudi"), "karaoke")
        self.assertEqual(categorie_du_titre("Dîner-spectacle oriental"), "cabaret")
        self.assertEqual(categorie_du_titre("Open mic stand-up"), "humour")
        self.assertEqual(categorie_du_titre("STEPPERS SOUND SYSTEM Launch party"), "soundsystem")
        self.assertEqual(categorie_du_titre("Becoming The Ocean - BIM'26"), "")

    def test_categorie_nuit(self):
        from scrapers.commun import categorie_nuit
        self.assertEqual(categorie_nuit("musique", "Malouf au clair de lune"), "concert")
        self.assertEqual(categorie_nuit("theatre", "Le Fou"), "")            # une pièce : agenda culturel
        self.assertEqual(categorie_nuit("theatre", "Comedy night stand-up"), "humour")
        self.assertEqual(categorie_nuit("club", "Movie Night: UN FILS"), "")  # un film, même chez un club
        self.assertEqual(categorie_nuit("club", "Vernissage et DJ set"), "")
        self.assertEqual(categorie_nuit("club", "Halloween"), "club")

    def test_concerts_grand_tunis(self):
        from scrapers.sources import tunis_events
        src = {"id": "t", "nom": "t", "url": "https://tunis.events/concerts", "categorie": "musique",
               "options": {"pages": [{"url": "https://tunis.events/concerts", "categorie": "musique"}]}}
        with faux_reseau({"concerts": "tunis-events-concerts.html"}):
            evts = tunis_events.recuperer(src)
        self.assertEqual([e.titre for e in evts], ["Jaou Nights"])
        self.assertEqual(evts[0].debut, dt.datetime(FUTUR, 11, 21, 22, 0))
        self.assertEqual(evts[0].categorie, "musique")
        self.assertEqual(evts[0].image, "https://tunis.events/storage/a.jpg")


class Instagram(unittest.TestCase):
    def test_affiche_par_evenement(self):
        from scrapers import lecteurs
        auj = dt.date.today()
        j = auj + dt.timedelta(days=5)
        pubs = [{"lien": "https://instagram.com/p/1", "date": auj.isoformat(), "images": ["assets/x.jpg"],
                 "texte": f"🔥 JAOU NIGHTS 🔥\nSamedi {j.day:02d}/{j.month:02d} dès 23h\n📍 B7L9, La Marsa\n#tunis #gammarth", "ocr": ""},
                {"lien": "https://instagram.com/p/2", "date": auj.isoformat(), "images": [],
                 "texte": "Merci pour hier soir ! #throwback", "ocr": ""},
                {"lien": "https://instagram.com/p/3", "date": auj.isoformat(), "images": [],
                 "texte": f"LE HABIBI RECRUTE ! Entretiens le {j.day:02d}/{j.month:02d}", "ocr": ""}]
        evts = lecteurs.une_affiche_par_evenement(pubs, [], "Habibi Downtown")
        self.assertEqual(len(evts), 1)
        self.assertEqual(evts[0].titre, "JAOU NIGHTS")
        self.assertEqual(evts[0].debut, dt.datetime(j.year, j.month, j.day, 23, 0))
        self.assertEqual(evts[0].image, "assets/x.jpg")
        self.assertEqual(evts[0].lieu, "B7L9, La Marsa")

    def test_titre_et_lieu_de_soiree(self):
        from scrapers import lecteurs
        j = dt.date.today() + dt.timedelta(days=6)
        pubs = [{"lien": "https://facebook.com/p/1", "date": dt.date.today().isoformat(), "images": [], "ocr": "",
                 "texte": "Some of the best selectors djs and producers of Bass Music will be playing tonight, all day long.\n\n"
                          f"Welcome to the STEPPERS SOUND SYSTEM Launch party.\n{j.day:02d}/{j.month:02d}, at @dar_ziqua in Zaghouan."}]
        evts = lecteurs.une_affiche_par_evenement(pubs, [], "Lieu à préciser")
        self.assertEqual([(e.titre, e.lieu) for e in evts], [("STEPPERS SOUND SYSTEM Launch party", "Dar Ziqua, Zaghouan")])

    def test_dates_en_anglais(self):
        from scrapers import lecteurs
        ref = dt.date(2026, 10, 31)
        self.assertEqual(lecteurs.jours_anglais("Launch party. November 8th, at @dar_ziqua", ref), ["2026-11-08"])
        self.assertEqual(lecteurs.jours_anglais("Sat 8th of Nov · Fri Dec. 12", ref), ["2026-11-08", "2026-12-12"])
        self.assertEqual(lecteurs.jours_anglais("May be an image of text, from 12h to 21h", ref), [])

    def test_lecture_apify(self):
        from scrapers.sources import instagram
        j = dt.date.today() + dt.timedelta(days=3)
        items = [{"url": "https://www.instagram.com/p/abc/", "type": "Image", "timestamp": "2026-11-01T10:00:00.000Z",
                  "displayUrl": "https://cdn/x.jpg", "caption": "Concert live au bar"}]
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.dict("os.environ", {"APIFY_TOKEN": "x"}), \
             mock.patch.object(instagram, "appeler_apify", return_value=items), \
             mock.patch.object(instagram, "DOSSIER_IMAGES", Path(d)), \
             mock.patch.object(instagram, "enregistrer_image", return_value="assets/programmes/t/a.jpg"), \
             mock.patch.object(instagram, "lire_image", return_value=f"{j.day:02d}.{j.month:02d} 21H30"):
            evts = instagram.recuperer({"id": "t", "nom": "Bar", "url": "bar", "categorie": "musique",
                                        "options": {"compte": "bar", "lieu": "Le Bar"}})
        self.assertEqual(len(evts), 1)
        self.assertEqual((evts[0].debut.hour, evts[0].debut.minute), (21, 30))
        self.assertEqual(evts[0].categorie, "musique")
        self.assertEqual(evts[0].lieu, "Le Bar")


class Propositions(unittest.TestCase):
    def test_issue_vers_evenement(self):
        from scrapers import propositions
        corps = ("### Titre\n\nConcert de oud\n\n### Date et heure\n\n2026-11-21 20h30\n\n"
                 "### Date de fin (facultatif)\n\n_No response_\n\n### Lieu\n\nDar Lasram\n\n"
                 "### Catégorie\n\nConcert live\n\n### Prix (facultatif)\n\nGratuit\n\n### Lien\n\nhttps://instagram.com/x\n\n"
                 "### Description et affiche (facultatif)\n\nUne soirée.\n\n"
                 "![affiche](https://github.com/user-attachments/assets/abc-123)")
        nom, contenu = propositions.evenement(corps, "42")
        self.assertEqual(nom, "2026-11-21-concert-de-oud.md")
        self.assertIn("date: 2026-11-21 20:30\n", contenu)
        self.assertIn('category: "concert"', contenu)
        self.assertIn('image: "https://github.com/user-attachments/assets/abc-123"', contenu)
        self.assertNotIn("end_date", contenu)
        self.assertTrue(contenu.rstrip().endswith("Une soirée."))

    def test_date_illisible(self):
        from scrapers import propositions
        with self.assertRaises(ValueError):
            propositions.evenement("### Titre\n\nX\n\n### Date et heure\n\nsamedi soir\n")


class Fiches(unittest.TestCase):
    def test_famille_et_notice(self):
        from scrapers.commun import est_famille, resume
        self.assertTrue(est_famille("Contes en scène", "Spectacle jeune public dès 5 ans"))
        self.assertTrue(est_famille("عرض للأطفال"))
        self.assertFalse(est_famille("Concert de jazz"))
        self.assertLessEqual(len(resume("Une phrase. " * 100, 100)), 100)
        # dans une notice, « enfants » seul ne suffit pas
        self.assertFalse(est_famille("Dar El 3ers", "Deux familles préparent le mariage de leurs enfants."))
        self.assertTrue(est_famille("Philo-Art", "Un atelier pour les enfants de 6 à 10 ans."))

    def test_alerte_apify(self):
        from scrapers.credit_apify import alerte
        self.assertEqual(alerte({"depense": 1, "limite": 5, "pourcent": 20, "fin_cycle": ""}), "")
        self.assertIn("épuisé", alerte({"depense": 5.1, "limite": 5, "pourcent": 102, "fin_cycle": "2026-12-01"}))
        self.assertIn("presque", alerte({"depense": 4.2, "limite": 5, "pourcent": 84, "fin_cycle": ""}))

    def test_presse_sans_sorties_de_film(self):
        from scrapers.sources.presse import est_sortie_de_film
        self.assertTrue(est_sortie_de_film("Cinéma : Le Temps suspendu, un film hongrois à ne pas rater"))
        self.assertFalse(est_sortie_de_film("JCC 2026 : les films de la compétition", "Le festival s'ouvre le 12 décembre"))
        self.assertFalse(est_sortie_de_film("Ciné-club : projection de Nahla au CinéMadart"))

    def test_age_conseille(self):
        from scrapers.commun import age_conseille
        self.assertEqual(age_conseille("Spectacle jeune public dès 5 ans"), "5")
        self.assertEqual(age_conseille("Atelier pour les 6-10 ans"), "6-10")
        self.assertEqual(age_conseille("ورشة للأطفال من 7 سنوات"), "7")
        self.assertIsNone(age_conseille("Festival, 20 ans de création"))

    def test_notice_sans_markdown(self):
        from scrapers.ecriture import _texte_brut
        self.assertEqual(_texte_brut("#tunis {{x}}\n- liste"), "\\#tunis x\n\\- liste")

    def test_artistes_des_titres(self):
        from scrapers.pages import artistes_des_titres
        noms = artistes_des_titres([{"title": "Kteb Tounsi Avec Sonia Hanihina"}, {"title": "2 Jours Avec Papa"},
                                    {"title": "Café Philo avec Azza Filali"}])
        self.assertEqual(sorted(noms.values()), ["Azza Filali", "Sonia Hanihina"])

    def test_role_conferencier(self):
        from scrapers.pages import role
        evts = [{"title": "Café Philo avec Azza Filali", "category": "autre"},
                {"title": "Kteb Tounsi : Rencontre-débat avec Sonia Hanihina"},
                {"title": "Avec Hafida Ben Rejeb Latta", "category": "litterature"},
                {"title": "Concert de Emel Mathlouthi", "category": "musique"},
                {"title": "Fabrika Festival", "category": "musique", "artists": ["Hugo Martinez"]},
                {"title": "Conférence : Hugo Martinez"}]
        self.assertEqual(role(["azza filali"], evts), "conferencier")
        self.assertEqual(role(["sonia hanihina"], evts), "conferencier")
        self.assertEqual(role(["hafida ben rejeb latta"], evts), "conferencier")
        self.assertEqual(role(["emel mathlouthi"], evts), "artiste")
        self.assertEqual(role(["hugo martinez"], evts), "conferencier")  # 1 conférence, 1 line-up : égalité
        self.assertEqual(role(["inconnu"], evts), "artiste")

    def test_type_lieu(self):
        from scrapers.pages import type_lieu, types_lieux
        c = types_lieux()
        self.assertEqual(type_lieu("Cinéma Le Colisée", "x", c, {}), "cinema")
        self.assertEqual(type_lieu("Salle de cinéma, Institut français de Sousse", "x", c, {}), "cinema")
        self.assertEqual(type_lieu("Théâtre municipal de Tunis", "x", c, {}), "theatre")
        self.assertEqual(type_lieu("El Teatro", "x", c, {}), "theatre")
        self.assertEqual(type_lieu("قاعة رشاد المناعي بقاعة الفن الرابع", "x", c, {}), "theatre")
        self.assertEqual(type_lieu("Galerie, Institut français de Sousse", "x", c, {}), "galerie")
        self.assertEqual(type_lieu("Institut français de Tunis", "x", c, {}), "centre")
        self.assertEqual(type_lieu("Shanti", "x", c, {}), "club")  # choisi à la main
        self.assertEqual(type_lieu("Le Rio", "le-rio", c, {"lieu:le-rio": {"type": "cinema"}}), "cinema")  # OSM
        self.assertEqual(type_lieu("Douz", "douz", c, {}), "autre")

    def test_type_osm(self):
        from scrapers.enrichir import osm_index
        i = osm_index([{"tags": {"name": "Le Rio", "amenity": "cinema"}}, {"tags": {"name": "Rien"}}])
        self.assertEqual(i, {"rio": {"type": "cinema"}})

    def test_lieux_regroupes(self):
        from scrapers.pages import lieux
        g = lieux([{"venue": "L'Agora Marsa"}, {"venue": "L’Agora La Marsa"}, {"venue": "Tunis"},
                   {"venue": "Théâtre de l'Opéra"}, {"venue": "Theatre de l’Opera"}])
        self.assertEqual(len(g), 2)

    def test_salle_ift(self):
        from scrapers.sources.pdf_programme import _salle
        self.assertEqual(_salle("alle de cinéma"), "Salle de cinéma")
        self.assertEqual(_salle("2024, 1h18mn, Médiathèque"), "Médiathèque")


class Lot7(unittest.TestCase):
    def test_resident_advisor(self):
        from scrapers.sources.resident_advisor import depuis_listes
        d = {"eventListings": {"data": [{"event": {
            "id": "1", "title": "Syndicate of Love", "date": "2026-11-20T00:00:00.000",
            "startTime": "2026-11-20T23:00:00.000", "endTime": "2026-11-21T05:00:00.000",
            "contentUrl": "/events/1", "cost": "30 TND",
            "venue": {"name": "Yuka", "address": "Gammarth", "area": {"name": "All"}}, "images": []}}]}}
        e = depuis_listes(d)[0]
        self.assertEqual((e.titre, e.debut.hour, e.fin, e.lien, e.prix), ("Syndicate of Love", 23, None, "https://ra.co/events/1", "30 TND"))

    def test_resident_advisor_line_up(self):
        from scrapers.sources.resident_advisor import depuis_listes
        soiree = {"id": "2", "title": "ONWRD", "startTime": "2026-11-03T19:00:00.000", "contentUrl": "/events/2",
                  "venue": {"name": "TBA", "area": {"name": "Tunis"}}, "images": [],
                  "artists": [{"name": "Amine K"}, {"name": "Deena Abdelwahed"}], "promoters": [{"name": "Downtown Vibes"}],
                  "content": "<p>Une nuit</p>"}
        d = {"eventListings": {"data": [{"event": soiree}, {"event": soiree}]}}
        evts = depuis_listes(d)
        self.assertEqual(len(evts), 1)  # la même soirée listée sur deux jours
        self.assertEqual(evts[0].artistes, ["Amine K", "Deena Abdelwahed"])
        self.assertEqual(evts[0].lieu, "Tunis")
        self.assertIn("Line-up : Amine K, Deena Abdelwahed", evts[0].description)
        self.assertIn("Organisé par Downtown Vibes", evts[0].description)

    def test_source_pas_un_lieu(self):
        from scrapers import pages
        sources = [{"id": "w", "nom": "Webdo", "genre": "presse"},
                   {"id": "k", "nom": "Kadhem (Instagram)", "genre": "collectif", "options": {"lieu": "Kadhem"}},
                   {"id": "f", "nom": "Fabrika festival (Instagram)", "genre": "festival", "options": {"lieu": "One Resort, Monastir"}},
                   {"id": "c", "nom": "Cité des sciences (Facebook)", "genre": "lieu"}]
        faux = pages.faux_lieux(sources)
        self.assertIn("webdo", faux)
        self.assertIn("kadhem", faux)
        self.assertNotIn("one resort", faux)
        evts = [{"venue": "Kadhem"}, {"venue": "One Resort"}, {"venue": "Webdo"}, {"venue": "Lieu à préciser"}]
        self.assertEqual([g["noms"].most_common(1)[0][0] for g in pages.lieux(evts, faux).values()], ["One Resort"])

    def test_genre_des_sources(self):
        import yaml
        from scrapers.commun import RACINE
        genres = yaml.safe_load((RACINE / "_data" / "genres.yml").read_text())
        for s in yaml.safe_load((RACINE / "_data" / "sources.yml").read_text()):
            self.assertIn(s.get("genre"), genres, f"{s['id']} : genre manquant ou inconnu")

    def test_alerte(self):
        import datetime as dt
        from unittest import mock
        from scrapers import alerte
        etat = {"a": {"dernier_non_vide": "2026-09-01T06:00:00"}, "b": {"premier_passage": "2026-11-01T06:00:00"}}
        sources = "- {id: a, nom: A, url: u}\n- {id: b, nom: B, url: u}\n- {id: c, nom: C, url: u, actif: false}\n"
        with mock.patch.object(alerte, "lire_etat", return_value=etat), \
             mock.patch("pathlib.Path.read_text", return_value=sources):
            liste = alerte.silencieuses(dt.datetime(2026, 11, 10))
        self.assertEqual([s["id"] for s, _, _ in liste], ["a"])
        self.assertIn("| 69 |", alerte.rapport(liste))


class Agora(unittest.TestCase):
    def test_billetterie_woocommerce(self):
        import datetime as dt
        from scrapers.sources.woocommerce_seances import depuis_produits
        produits = [{"name": "L&rsquo;Île des Souvenirs", "permalink": "https://lagora.tn/produit/lile-des-souvenirs/",
                     "prices": {"price": "13000", "currency_minor_unit": 3},
                     "images": [{"src": "https://lagora.tn/a.jpg"}], "description": "<p>Deux femmes…</p>",
                     "attributes": [{"name": "Séances", "terms": [{"name": "Dim. 1 novembre - 15:00 - VF"},
                                                                  {"name": "Ven. 30 octobre - 16:00 - VF"}]},
                                    {"name": "Type du Ticket", "terms": [{"name": "Adulte"}]}]},
                    {"name": "Sans séance", "attributes": []}]
        evts = depuis_produits(produits, {"nom": "L'Agora", "url": "https://lagora.tn", "options": {"lieu": "L'Agora Marsa"}},
                               dt.date(2026, 11, 1))
        self.assertEqual(len(evts), 1)
        e = evts[0]
        self.assertEqual((e.titre, e.debut, e.prix, e.film), ("L’Île des Souvenirs", dt.datetime(2026, 11, 1, 15), "13 DT", True))


class Expositions(unittest.TestCase):
    def test_expo_vernissage_passe(self):
        import datetime as dt
        from unittest import mock
        from scrapers import lecteurs
        pub = {"lien": "https://www.instagram.com/p/x/", "date": "2026-10-25", "images": ["a.jpg"],
               "texte": "COSMOSE\\nSolo exhibition de Halim Karabibene.\\nVernissage le 29 octobre à partir de 18h.", "ocr": ""}
        pub["texte"] = pub["texte"].replace("\\\\n", "\\n")
        class Jour(dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 1)
        with mock.patch.object(lecteurs.dt, "date", Jour):
            evts = lecteurs.une_affiche_par_evenement([pub], [], "Agorgi Gallery")
        self.assertEqual(len(evts), 1)
        e = evts[0]
        self.assertEqual((e.categorie, e.debut.date().isoformat(), e.fin.date().isoformat()), ("expo", "2026-10-29", "2026-11-28"))

    def test_annonces_et_meme_expo(self):
        import datetime as dt
        from unittest import mock
        from scrapers import lecteurs
        pubs = [
            {"lien": "a", "date": "2026-10-19", "texte": "Dix ans après sa dernière exposition personnelle, Halim Karabibene revient avec Cosmose. Jusqu'au 18 novembre."},
            {"lien": "b", "date": "2026-10-28", "texte": "COSMOSE\nExposition de Halim Karabibene. Vernissage le 30 octobre."},
            {"lien": "c", "date": "2026-10-28", "texte": "تعلم لجنة تنظيم أيام قرطاج السينمائية أنه تم فتح باب الاعتماد للصحفيين يوم 23 نوفمبر"},
            {"lien": "d", "date": "2026-10-28", "texte": "L'Agenda culturel de la Méditerranée : novembre, le 9 novembre"},
            {"lien": "e", "date": "2026-10-28", "texte": "Soirée théâtre le 5 novembre à 20h, prochaine édition le 30 janvier"},
        ]
        class Jour(dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 1)
        with mock.patch.object(lecteurs.dt, "date", Jour):
            evts = lecteurs.une_affiche_par_evenement(pubs, [], "Agorgi Gallery")
        self.assertEqual(sorted(e.lien for e in evts), ["b", "e"])
        self.assertEqual([e.debut.date().isoformat() for e in evts if e.lien == "e"], ["2026-11-05"])

    def test_autre_ville_dans_le_titre(self):
        import datetime as dt
        from scrapers import ecriture
        from scrapers.commun import Evenement
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ecriture, "DOSSIER_AUTO", Path(d)):
            src = {"id": "ig-la-boite", "nom": "La Boîte (Instagram)", "genre": "lieu", "options": {"lieu": "La Boîte"}}
            ecriture.ecrire_evenements(src, [Evenement("Direction Gabès pour les Oasis Days !", dt.datetime(2030, 11, 3), "x", "La Boîte")])
            texte = next(Path(d).rglob("*.md")).read_text()
        self.assertIn('venue: "Gabès, voir l\'annonce"', texte)
        self.assertIn('ville: "sud"', texte)

    def test_annee_par_jour_de_semaine(self):
        import datetime as dt
        from scrapers.sources.woocommerce_seances import seances
        auj = dt.date(2026, 11, 1)
        # vieux produit : le 3 février était un mardi en 2026 (pas en 2027)
        self.assertEqual(seances(["Mar. 3 février - 19:15 - VO"], auj), ["2026-02-03 19:15"])
        self.assertEqual(seances(["Dim. 1 novembre - 15:00 - VF"], auj), ["2026-11-01 15:00"])
        self.assertEqual(seances(["Ven. 1 janvier - 20:00 - VF"], auj), ["2027-01-01 20:00"])


class AgoraDjerba(unittest.TestCase):
    def test_publicite_sans_film_ignoree(self):
        import datetime as dt
        from unittest import mock
        from scrapers import lecteurs
        pub = {"lien": "https://www.instagram.com/p/x/", "date": "2026-11-01", "images": ["a.jpg"],
               "texte": "Retrouvez tous les horaires sur l'application L'AGORA Cinéma 📱 ou sur www.lagoradjerba.tn\\n"
                        "Évitez la file d'attente, réservez vos places dès maintenant ! 🎟️",
               "ocr": "Mardi 3 novembre 2026 16:30"}
        class Jour(dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 2)
        with mock.patch.object(lecteurs.dt, "date", Jour):
            self.assertEqual(lecteurs.une_affiche_par_evenement([pub], [], "L'Agora Djerba"), [])

    def test_publicite_agora_marsa_et_filtre_cinema(self):
        import datetime as dt
        from unittest import mock
        from scrapers import lecteurs
        from scrapers.sources import instagram
        pub = {"lien": "https://www.instagram.com/p/y/", "date": "2026-10-30", "images": ["a.jpg"],
               "texte": "🎬 Cette semaine, ton prochain coup de cœur ciné t'attend à L'Agora ! 🍿 Du 2 au 8 novembre",
               "ocr": ""}
        class Jour(dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 11, 2)
        with mock.patch.object(lecteurs.dt, "date", Jour):
            self.assertEqual(lecteurs.une_affiche_par_evenement([pub], [], "L'Agora Marsa"), [])
        # source de cinéma : un événement sans film connu est écarté
        e = lecteurs.Evenement(titre="Soirée à L'Agora", debut=dt.datetime(2026, 11, 2), lien="x") \
            if hasattr(lecteurs, "Evenement") else None
        if e:
            src = {"id": "t", "nom": "T", "url": "https://x", "categorie": "cinema", "options": {"lieu": "T"}}
            with mock.patch.object(instagram, "lire_publications", return_value=[]), \
                 mock.patch.dict(lecteurs.LECTEURS, {"une_affiche_par_evenement": lambda *a, **k: [e]}), \
                 mock.patch.object(lecteurs, "titres_connus", return_value=["Le Mystère Lucy Lost"]):
                self.assertEqual(instagram.recuperer(src), [])

    def test_rattacher_les_evenements_a_leur_festival(self):
        import datetime as dt
        from scrapers import festivals
        fs = [{"id": "jaou", "nom": "Jaou Tunis", "mots": "Jaou", "debut": dt.date(2026, 10, 23), "fin": dt.date(2026, 11, 22)},
              {"id": "jtc", "nom": "JTC", "mots": "Journées Théâtrales de Carthage|JTC", "debut": dt.date(2026, 11, 21), "fin": dt.date(2026, 11, 28)}]
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ift").mkdir()
            for nom, titre, date, corps in [
                ("a", "Images de Syrie", "2026-10-27 18:00", "Dans le cadre du festival Jaou Tunis 2026, l'exposition…"),  # cité dans la notice
                ("b", "Jaou Tunis : visite guidée", "2026-11-05 10:00", ""),                                              # dans le titre
                ("c", "Jaou Tunis 2027", "2027-10-30 10:00", ""),                                                         # une autre édition
                ("d", "Un concert JTC", "2026-11-02 20:00", "Soirée"),                                                     # sigle, hors dates
                ("e", "Concert de oud", "2026-11-05 20:00", "Au Jaouhar club")]:                                           # mot partiel
                (d / "ift" / f"{nom}.md").write_text(
                    f'---\ntitle: "{titre}"\ndate: {date}\nvenue: "Tunis"\nsource: "ift"\nauto: true\n---\n{corps}\n')
            self.assertEqual(festivals.rattacher(fs, d), 2)
            lu = {n: (d / "ift" / f"{n}.md").read_text() for n in "abcde"}
            self.assertIn('festival: "jaou"', lu["a"])
            self.assertIn('festival: "jaou"', lu["b"])
            for n in "cde":
                self.assertNotIn("festival:", lu[n])
            self.assertIn("date: 2026-10-27 18:00\n", lu["a"])
            self.assertEqual(festivals.rattacher(fs, d), 2)  # relancer ne change rien
            # « Jaou » tout court, sans heure : annonce de remplissage, masquée
            (d / "ift" / "g.md").write_text('---\ntitle: "Jaou Tunis"\ndate: 2026-11-06\nvenue: "Tunis"\nsource: "ift"\nauto: true\n---\n')
            festivals.rattacher(fs, d)
            self.assertIn("doublon: true", (d / "ift" / "g.md").read_text())
            self.assertNotIn("doublon", (d / "ift" / "b.md").read_text())
            (d / "ift" / "g.md").unlink()
            # séries : mêmes mots, mais pas de contrainte de dates
            serie = [{"id": "kteb", "nom": "Kteb Tounsi", "mots": "Kteb Tounsi"}]
            (d / "ift" / "f.md").write_text('---\ntitle: "Kteb Tounsi : rencontre avec Sonia"\ndate: 2027-03-04 18:00\nvenue: "Tunis"\nsource: "ift"\nauto: true\n---\n')
            self.assertEqual(festivals.rattacher(fs, d, serie), 3)
            self.assertIn('serie: "kteb"', (d / "ift" / "f.md").read_text())
            self.assertNotIn("festival:", (d / "ift" / "f.md").read_text())

    def test_hors_culture(self):
        from scrapers.commun import pas_un_evenement
        self.assertTrue(pas_un_evenement("Action De Sensibilisation Et De Prévention Du Diabète"))
        self.assertTrue(pas_un_evenement("Journée de dépistage gratuit"))
        self.assertTrue(pas_un_evenement("JAOU TUNIS 26 - Full Fest Access"))  # un pass, pas un spectacle
        self.assertFalse(pas_un_evenement("Concert de oud à El Teatro"))


class RetourBeta(unittest.TestCase):
    """Retour d'une testeuse (3 novembre 2026) : catégories, festivals transversaux, lieux de référence."""

    def test_proposition_nouvelles_categories(self):
        from scrapers import propositions
        corps = "### Titre\n\nX\n\n### Date et heure\n\n2026-12-01\n\n### Catégorie\n\nCabaret\n"
        self.assertIn('category: "cabaret"', propositions.evenement(corps)[1])
        corps = corps.replace("Cabaret", "Festival & open air")
        self.assertIn('category: "festival"', propositions.evenement(corps)[1])

    def test_la_boite_est_un_centre_d_art(self):
        from scrapers import pages
        config = pages.types_lieux()
        self.assertEqual(pages.type_lieu("La Boîte", "la-boite", config, {}), "centre_art")
        self.assertEqual(pages.type_lieu("Club Le Boîte de nuit", "x", config, {}), "club")

    def test_annonce_de_partenariat(self):
        notice = ("L'Institut français de Tunisie est fier d'être partenaire de la 8e édition de \"Jaou Tunis "
                  "Biennale 2026\" qui se tiendra du 23 octobre au 22 novembre.")
        self.assertTrue(commun.annonce_de_partenariat(notice))
        self.assertFalse(commun.annonce_de_partenariat("Concert de jazz. Entrée libre, avec le soutien de la mairie."))


class Libelles(unittest.TestCase):
    def test_textes_retenus(self):
        from scrapers.libelles import retenu
        self.assertTrue(retenu("Musée national du Bardo"))
        self.assertTrue(retenu("11 rue Nelson Mandela, La Marsa"))
        self.assertFalse(retenu("À partir de 20 DT"))
        self.assertFalse(retenu("https://exemple.org/page web"))
        self.assertFalse(retenu("Mo-Su 07:30 - 17:30"))
        self.assertFalse(retenu("bardo"))

    def test_traduction_gardee_une_fois(self):
        from scrapers import libelles

        class Faux:
            appels = 0

            def traduire(self, textes, de, vers):
                Faux.appels += 1
                return [f"{vers}:{t}" for t in textes]

        cache = {}
        n = libelles.traduire_libelles(Faux(), cache, {"Médiathèque de Tunis"})
        self.assertEqual(n, 1)
        self.assertEqual(cache["Médiathèque de Tunis"]["en"], "en:Médiathèque de Tunis")
        self.assertEqual(cache["Médiathèque de Tunis"]["de"], "fr")
        avant = Faux.appels
        libelles.traduire_libelles(Faux(), cache, {"Médiathèque de Tunis"})
        self.assertEqual(Faux.appels, avant)
