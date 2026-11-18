"""Soirées récurrentes (_data/recurrentes.yml) : prochaines dates, fin après minuit, preuve trop ancienne."""
import datetime as dt
import unittest

from scrapers.sources import recurrentes


class Recurrentes(unittest.TestCase):
    LUNDI = dt.date(2026, 11, 16)

    def entree(self, **autres):
        x = {"titre": "Open Mic", "lieu": "Rock'n'Rolla", "jours": "mardi", "heure": "21:00",
             "lien": "https://instagram.com/x", "categorie": "karaoke", "verifie_le": "2026-11-10"}
        x.update(autres)
        return x

    def test_deux_semaines(self):
        evts = recurrentes.evenements([self.entree()], self.LUNDI)
        self.assertEqual([e.debut for e in evts], [dt.datetime(2026, 11, 17, 21), dt.datetime(2026, 11, 24, 21)])

    def test_plusieurs_jours_et_exception(self):
        evts = recurrentes.evenements([self.entree(jours=["vendredi", "samedi"], sauf=["2026-11-21"])], self.LUNDI)
        self.assertEqual([e.debut.date().isoformat() for e in evts], ["2026-11-20", "2026-11-27", "2026-11-28"])

    def test_fin_le_lendemain(self):
        e = recurrentes.evenements([self.entree(heure="23:00", fin="04:00")], self.LUNDI)[0]
        self.assertEqual(e.fin, dt.datetime(2026, 11, 18, 4, 0))

    def test_preuve_trop_ancienne(self):
        self.assertEqual(recurrentes.evenements([self.entree(verifie_le="2026-08-01")], self.LUNDI), [])
        self.assertEqual(recurrentes.evenements([self.entree(verifie_le=None)], self.LUNDI), [])


if __name__ == "__main__":
    unittest.main()
