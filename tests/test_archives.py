import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scrapers.archives import _ajouter, _lire

FICHE = """---
title: "Concert de oud"
date: 2026-10-07 20:30:00
venue: "El Teatro"
ville: "tunis"
category: "musique"
link: "https://exemple.tn/oud"
---
Un **récital** de oud.
"""


class TestArchives(unittest.TestCase):
    def test_lire(self):
        e = _lire(FICHE, "_events/auto/x/2026-10-07-concert.md")
        self.assertEqual(e["titre"], "Concert de oud")
        self.assertEqual((e["debut"], e["fin"], e["heure"]), ("2026-10-07", "2026-10-07", "20:30"))
        self.assertEqual(e["resume"], "Un récital de oud.")

    def test_doublon_et_film_ignores(self):
        self.assertIsNone(_lire(FICHE.replace("ville:", "doublon: true\nville:"), "x"))
        self.assertIsNone(_lire(FICHE.replace("ville:", "film: true\nville:"), "x"))

    def test_ajouter_seulement_passe_et_une_fois(self):
        annees = {}
        e = _lire(FICHE, "x")
        self.assertFalse(_ajouter(annees, e, "2026-10-07"))  # encore en cours ce jour-là
        self.assertTrue(_ajouter(annees, e, "2026-10-08"))
        self.assertFalse(_ajouter(annees, dict(e, fichier="y"), "2026-10-08"))
        self.assertEqual(list(annees), ["2026"])


    def test_charger_ignore_index(self):
        """index.json (décompte par année) n'est pas un fichier d'événements : il faisait planter l'archivage."""
        from scrapers import archives
        e = {"titre": "A", "debut": "2026-11-01", "fin": "2026-11-01", "heure": "", "lieu": "Lieu", "source": "", "fichier": "x"}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "2026.json").write_text(json.dumps([e]))
            (Path(d) / "index.json").write_text(json.dumps({"2026": 1}))
            with mock.patch.object(archives, "DOSSIER", Path(d)):
                self.assertEqual(list(archives._charger()), ["2026"])


if __name__ == "__main__":
    unittest.main()
