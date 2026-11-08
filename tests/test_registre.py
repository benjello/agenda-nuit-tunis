"""Registre des sources : vérifie _data/sources.yml et _data/sources_recherchees.yml.

  python3 -m unittest tests.test_registre -v

Ces tests protègent les contributions extérieures (pull requests) : une entrée mal écrite
échoue ici avant d'arriver sur le site ou de faire planter les scrapers.
"""
import re
import unittest

import yaml

from scrapers.commun import RACINE

ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
TYPES = {"lieu", "billetterie", "cinema", "agenda"}
GENRES = {"lieu", "institution", "festival", "collectif", "administration", "presse", "agenda"}
CHAMPS = {"id", "nom", "url", "type", "genre", "scraper", "categorie", "actif", "options",
          "tous_les_jours", "note", "fiche", "nom_fiche"}


def lire(nom):
    return yaml.safe_load((RACINE / "_data" / nom).read_text(encoding="utf-8")) or []


class Registre(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = lire("sources.yml")
        cls.categories = set(lire("categories.yml"))
        cls.scrapers = {p.stem for p in (RACINE / "scrapers" / "sources").glob("*.py")} - {"__init__"}

    def test_ids_uniques_et_bien_formes(self):
        vus = set()
        for s in self.sources:
            with self.subTest(source=s.get("id")):
                self.assertTrue(ID.fullmatch(str(s.get("id", ""))), "id : minuscules, chiffres et tirets")
                self.assertNotIn(s["id"], vus, "id déjà pris")
                vus.add(s["id"])

    def test_champs(self):
        for s in self.sources:
            with self.subTest(source=s.get("id")):
                self.assertLessEqual(set(s), CHAMPS, "champ inconnu (faute de frappe ?)")
                for champ in ("nom", "url", "type", "genre", "scraper", "actif"):
                    self.assertIn(champ, s)
                self.assertIn(s["type"], TYPES)
                self.assertIn(s["genre"], GENRES)
                self.assertIsInstance(s["actif"], bool)
                if s.get("categorie") is not None:
                    self.assertIn(s["categorie"], self.categories)
                if s.get("tous_les_jours") is not None:
                    self.assertIsInstance(s["tous_les_jours"], int)
                if s.get("options") is not None:
                    self.assertIsInstance(s["options"], dict)

    def test_source_active_lisible(self):
        """Une source active doit avoir une adresse https et un scraper qui existe."""
        for s in self.sources:
            if not s["actif"]:
                continue
            with self.subTest(source=s["id"]):
                self.assertIn(s["scraper"], self.scrapers, "scraper inconnu (dossier scrapers/sources/)")
                self.assertTrue(str(s["url"]).startswith("https://"), "adresse en https:// attendue")


class Recherchees(unittest.TestCase):
    def test_entrees(self):
        recherchees = lire("sources_recherchees.yml")
        categories = set(lire("categories.yml"))
        sources = {s["id"] for s in lire("sources.yml")}
        vus = set()
        for r in recherchees:
            with self.subTest(recherche=r.get("id")):
                self.assertTrue(ID.fullmatch(str(r.get("id", ""))))
                self.assertNotIn(r["id"], vus)
                vus.add(r["id"])
                self.assertLessEqual(set(r), {"id", "nom", "categorie", "cherche", "pistes", "source", "tache", "niveau"})
                self.assertTrue(r.get("nom") and r.get("cherche"))
                self.assertIn(r.get("tache"), {"trouver", "verifier", "brancher", "coder"})
                self.assertIn(r.get("niveau"), {"facile", "moyen", "avance"})
                self.assertIn(r.get("categorie", "autre"), categories)
                if r.get("source"):
                    self.assertIn(r["source"], sources, "source absente de _data/sources.yml")


class ResumeContribution(unittest.TestCase):
    def test_classer(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "resume_contribution", RACINE / ".github" / "scripts" / "resume_contribution.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        donnees, sensibles, autres = module.classer(
            ["_data/sources.yml", ".github/workflows/scrapers.yml", "scrapers/commun.py",
             "tests/fixtures/x.html", "tests/test_x.py", "README.md", "proposer.html"])
        self.assertEqual(donnees, ["_data/sources.yml", "tests/fixtures/x.html", "README.md"])
        self.assertEqual(sensibles, [".github/workflows/scrapers.yml", "scrapers/commun.py", "proposer.html"])
        self.assertEqual(autres, ["tests/test_x.py"])


if __name__ == "__main__":
    unittest.main()
