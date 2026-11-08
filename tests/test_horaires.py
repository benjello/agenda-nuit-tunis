"""Horaires : heure de début et de fin lues dans les annonces, écrites dans le front matter.

  python3 -m unittest tests.test_horaires -v
"""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scrapers import ecriture, lecteurs
from scrapers.commun import Evenement, horaire_du_texte

FUTUR = dt.date.today().year + 1


class Lecture(unittest.TestCase):
    def test_plages(self):
        self.assertEqual(horaire_du_texte("Concert de 19h à 21h30"), ((19, 0), (21, 30)))
        self.assertEqual(horaire_du_texte("20:00 – 23:00"), ((20, 0), (23, 0)))
        self.assertEqual(horaire_du_texte("10h à 18h"), ((10, 0), (18, 0)))

    def test_heure_seule(self):
        self.assertEqual(horaire_du_texte("Rendez-vous à 20h30"), ((20, 30), None))
        self.assertEqual(horaire_du_texte("Doors 9pm"), ((21, 0), None))
        self.assertEqual(horaire_du_texte("le 12.11.2026 à 19:00"), ((19, 0), None))

    def test_pas_d_heure_inventee(self):
        for t in ("", "du 3 au 5 novembre", "Entrée 5 DT", "18h-20h puis 21h-23h", "samedi 17h30 et dimanche à 15h"):
            self.assertEqual(horaire_du_texte(t), (None, None), t)


class Ecriture(unittest.TestCase):
    def ecrire(self, e):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(ecriture, "DOSSIER_AUTO", Path(tmp)):
            ecriture.ecrire_evenements({"id": "essai", "nom": "Essai"}, [e])
            return next((Path(tmp) / "essai").glob("*.md")).read_text()

    def test_heure_et_fin_de_la_notice(self):
        e = Evenement("Récital", dt.datetime(FUTUR, 11, 5), "https://x.tn/r", lieu="Théâtre",
                      description="Récital de piano, de 19h à 21h.")
        txt = self.ecrire(e)
        self.assertIn(f"date: {FUTUR}-11-05 19:00", txt)
        self.assertIn('end_time: "21:00"', txt)
        self.assertNotIn("end_date", txt)

    def test_fin_donnee_par_la_source(self):
        e = Evenement("Concert", dt.datetime(FUTUR, 11, 5, 20), "https://x.tn/c", fin=dt.datetime(FUTUR, 11, 5, 22, 30))
        self.assertIn('end_time: "22:30"', self.ecrire(e))

    def test_soiree_apres_minuit(self):
        e = Evenement("Nuit", dt.datetime(FUTUR, 11, 5, 22), "https://x.tn/n", fin=dt.datetime(FUTUR, 11, 6, 4))
        txt = self.ecrire(e)
        self.assertIn('end_time: "04:00"', txt)
        self.assertNotIn("end_date", txt)

    def test_sans_heure_reste_sans_heure(self):
        txt = self.ecrire(Evenement("Expo", dt.datetime(FUTUR, 11, 5), "https://x.tn/e", description="Vernissage"))
        self.assertIn(f"date: {FUTUR}-11-05\n", txt)
        self.assertNotIn("end_time", txt)

    def test_plusieurs_jours_gardent_end_date(self):
        e = Evenement("Festival", dt.datetime(FUTUR, 11, 5), "https://x.tn/f", fin=dt.datetime(FUTUR, 11, 9),
                      description="Chaque soir à 20h")
        txt = self.ecrire(e)
        self.assertIn("end_date", txt)
        self.assertNotIn("end_time", txt)


class Affiches(unittest.TestCase):
    def test_plage_sur_affiche(self):
        d = dt.date.today() + dt.timedelta(days=10)
        pub = [{"lien": "https://i.tn/p/1", "date": dt.date.today().isoformat(), "images": [],
                "texte": f"Soirée Techno {d.day}/{d.month} de 22h à 4h", "ocr": ""}]
        evts = lecteurs.une_affiche_par_evenement(pub, [], "Club")
        self.assertEqual(len(evts), 1)
        self.assertEqual((evts[0].debut.hour, evts[0].fin.hour), (22, 4))
