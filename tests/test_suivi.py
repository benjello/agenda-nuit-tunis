"""Suivi des pannes : quelles sources ouvrent une issue, et ce que le script demande à gh."""
import json
import unittest

from scrapers.suivi import PREFIXE, pannes, synchroniser

SOURCES = [
    {"id": "a", "nom": "A", "url": "https://a.tn", "scraper": "x"},
    {"id": "b", "nom": "B", "url": "https://b.tn", "scraper": "x"},
    {"id": "c", "nom": "C", "url": "https://c.tn", "scraper": "x", "actif": False},
    {"id": "d", "nom": "D", "url": "https://d.tn", "scraper": "x"},
]


class TestPannes(unittest.TestCase):
    def test_tri(self):
        etat = {
            # en échec depuis deux jours : panne
            "a": {"ok": False, "erreur": "HTTPError: 404", "dernier_passage": "2026-11-18T06:20:00",
                  "dernier_succes": "2026-11-16T06:20:00"},
            # un seul passage raté : on attend
            "b": {"ok": False, "erreur": "Timeout", "dernier_passage": "2026-11-18T06:20:00",
                  "dernier_succes": "2026-11-17T06:20:00"},
            # en pause : rien
            "c": {"ok": False, "erreur": "x", "dernier_passage": "2026-11-18T06:20:00"},
            # jamais réussi : panne
            "d": {"ok": False, "erreur": "ValueError", "dernier_passage": "2026-11-18T06:20:00"},
        }
        self.assertEqual([s["id"] for s, _ in pannes(SOURCES, etat)], ["a", "d"])

    def test_attente_et_ok(self):
        etat = {"a": {"ok": True, "dernier_passage": "2026-11-18T06:20:00"},
                "b": {"ok": None, "attente": "clé manquante", "dernier_passage": "2026-11-18T06:20:00"}}
        self.assertEqual(pannes(SOURCES, etat), [])


class TestSynchroniser(unittest.TestCase):
    def test_ouvre_met_a_jour_ferme(self):
        appels = []

        def faux_gh(*args):
            appels.append(args)
            if args[:2] == ("issue", "list"):
                return json.dumps([{"number": 10, "title": PREFIXE + "a"},
                                   {"number": 11, "title": PREFIXE + "b"}])
            return ""

        e = {"ok": False, "erreur": "404", "dernier_passage": "2026-11-18T06:20:00"}
        fait = synchroniser([(SOURCES[0], e), (SOURCES[3], e)], faux_gh)
        self.assertEqual(fait, ["mise à jour #10 (a)", "ouverte (d)", "fermée #11 (b)"])
        creation = [a for a in appels if a[:2] == ("issue", "create")][0]
        self.assertIn(PREFIXE + "d", creation)
        self.assertIn("panne", creation)


if __name__ == "__main__":
    unittest.main()
