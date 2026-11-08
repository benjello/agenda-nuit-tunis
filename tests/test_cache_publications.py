"""Cache des publications Instagram / Facebook : on ne redemande à Apify que les nouvelles."""
import datetime as dt
import pathlib
import tempfile
import unittest
from unittest import mock

from scrapers.commun import Publication
from scrapers.sources import facebook_programmes as fp

SOURCE = {"id": "ig-essai", "options": {"jours": 21}}


def jour(n: int) -> str:
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


class CachePublications(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(fp, "CACHE", pathlib.Path(self.tmp.name))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_fenetre_complete_sans_cache(self):
        self.assertEqual(fp.fenetre(SOURCE), 21)

    def test_fenetre_depuis_derniere_lecture(self):
        fp.fusionner(SOURCE, [], 6)
        il_y_a_3j = (dt.datetime.now() - dt.timedelta(days=3, hours=1)).isoformat()
        with mock.patch("scrapers.ecriture.lire_etat", return_value={"ig-essai": {"ok": True, "dernier_succes": il_y_a_3j}}):
            self.assertEqual(fp.fenetre(SOURCE), 5)
        with mock.patch("scrapers.ecriture.lire_etat", return_value={"ig-essai": {"ok": False, "dernier_succes": il_y_a_3j}}):
            self.assertEqual(fp.fenetre(SOURCE), 21)

    def test_fusion_garde_les_anciennes_dans_la_fenetre(self):
        fp.fusionner(SOURCE, [Publication("a", jour(10)), Publication("vieille", jour(30)),
                              Publication("sans-image", jour(5), images=["assets/introuvable.jpg"])], 6)
        res = fp.fusionner(SOURCE, [Publication("b", jour(1), texte="nouveau")], 6)
        self.assertEqual([p.lien for p in res], ["b", "a"])
        self.assertEqual(set(fp.en_cache(SOURCE)), {"a", "b"})

    def test_fusion_limite(self):
        fp.fusionner(SOURCE, [Publication(str(i), jour(i)) for i in range(5)], 6)
        res = fp.fusionner(SOURCE, [Publication("n", jour(0))], 3)
        self.assertEqual([p.lien for p in res], ["n", "0", "1"])


if __name__ == "__main__":
    unittest.main()
