"""Le titre « Ce soir à Tunis » doit suivre l'heure des événements affichés (matin, après-midi, soir)."""
import unittest
from pathlib import Path

import yaml

RACINE = Path(__file__).resolve().parent.parent


class TitreCeSoir(unittest.TestCase):
    def test_libelles_dans_les_trois_langues(self):
        i18n = yaml.safe_load((RACINE / "_data" / "i18n.yml").read_text(encoding="utf-8"))
        for cle in ("ce_soir_titre", "ce_soir_matin", "ce_soir_apres_midi", "ce_soir_jour"):
            self.assertTrue({"fr", "ar", "en"} <= set(i18n[cle]), cle)

    def test_site_js_choisit_le_libelle_selon_l_heure(self):
        js = (RACINE / "assets" / "site.js").read_text(encoding="utf-8")
        for cle in ("ce_soir_matin", "ce_soir_apres_midi", "ce_soir_jour"):
            self.assertIn(cle, js)
        self.assertIn("'12:00'", js)
        self.assertIn("'17:00'", js)


if __name__ == "__main__":
    unittest.main()
