"""Quartiers du filtre téléphone : les motifs de _data/quartiers.yml compilent et rangent les lieux connus.

  python3 -m unittest tests.test_quartiers -v
"""
import re
import unicodedata
import unittest

import yaml

from scrapers.commun import RACINE


def norme(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def quartier(texte):
    for q in yaml.safe_load((RACINE / "_data" / "quartiers.yml").read_text(encoding="utf-8")):
        if re.search(q["motif"], norme(texte)):
            return q["id"]
    return ""


class TestQuartiers(unittest.TestCase):
    def test_lieux_connus(self):
        for lieu, attendu in [
            ("L'Agora Marsa, La Marsa", "marsa"),
            ("Creative Hub, Sidi Bou Saïd", "sidi-bou-said"),
            ("Beit al-Hikma, Carthage", "carthage"),
            ("Caserne El Attarine, Médina de Tunis", "medina"),
            ("Théâtre municipal de Tunis, 54 Ave Habib Bourguiba", "centre-ville"),
            ("Pathé Tunis City, Cebalat Ben Ammar", "nord"),
            ("Pathé Azur City, Radès, Ben Arous", "sud"),
            ("Sousse", ""),
        ]:
            self.assertEqual(quartier(lieu), attendu, lieu)


if __name__ == "__main__":
    unittest.main()
