"""Synchro BACKLOG.md et issues ouvertes (hors ligne) :

  python3 -m unittest tests.test_synchro_tickets -v
"""
import unittest

from scrapers.synchro_tickets import comparer, rapport, references

BACKLOG = """## Tickets ouverts
- [#106 festivals](https://github.com/x/y/issues/106), [#107 Presse](https://github.com/x/y/issues/107)

## À faire
- [ ] Trouver le PDF du programme (#108)
- [ ] Ouvrir une alerte quand une source tombe en panne
- [x] Fait et clos
"""


class Synchro(unittest.TestCase):
    def test_references_lit_les_deux_formes(self):
        self.assertEqual(references("#106 et https://github.com/x/y/issues/107"), {106, 107})

    def test_issue_citee_ou_absente(self):
        issues = [{"number": 106, "title": "a"}, {"number": 999, "title": "b"}]
        absentes, _ = comparer(BACKLOG, issues)
        self.assertEqual([i["number"] for i in absentes], [999])

    def test_case_sans_issue_signalee_seulement(self):
        _, cases = comparer(BACKLOG, [])
        self.assertEqual(cases, ["Ouvrir une alerte quand une source tombe en panne"])

    def test_case_cochee_ignoree(self):
        _, cases = comparer("- [x] Fait et clos\n", [])
        self.assertEqual(cases, [])

    def test_rapport_aligne_quand_rien_ne_manque(self):
        self.assertEqual(rapport([], []), "Backlog et issues ouvertes sont alignés.")

    def test_rapport_liste_les_ecarts(self):
        texte = rapport([{"number": 999, "title": "Oubliée"}], ["Une case"])
        self.assertIn("#999 Oubliée", texte)
        self.assertIn("- Une case", texte)


if __name__ == "__main__":
    unittest.main()
