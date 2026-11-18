import datetime as dt
import unittest
from unittest import mock

from scrapers import images

T = dt.datetime(2026, 11, 17, 12)


class TestImages(unittest.TestCase):
    def test_signatures(self):
        self.assertTrue(images.est_une_image(b"\xff\xd8\xff\xe0abc"))
        self.assertTrue(images.est_une_image(b"\x89PNG\r\n"))
        self.assertTrue(images.est_une_image(b"RIFF\x00\x00\x00\x00WEBP"))
        self.assertFalse(images.est_une_image(b"<html><body>403"))

    def test_locale(self):
        self.assertEqual(images.verifier_locale("assets/absent.jpg")[0], "cassee")

    def test_remplacement(self):
        f = images.mettre_a_jour(None, "cassee", "HTTP 403", T)
        self.assertTrue(images.a_remplacer(f))  # vraie erreur : tout de suite
        f = images.mettre_a_jour(None, "incertaine", "Timeout", T)
        self.assertFalse(images.a_remplacer(f))  # panne passagère : on attend
        f = images.mettre_a_jour(f, "incertaine", "Timeout", T)
        self.assertTrue(images.a_remplacer(f))
        f = images.mettre_a_jour(f, "ok", "", T)
        self.assertFalse(images.a_remplacer(f))

    def test_relecture(self):
        ok = images.mettre_a_jour(None, "ok", "", T)
        self.assertFalse(images.a_relire(ok, T + dt.timedelta(days=1)))
        self.assertTrue(images.a_relire(ok, T + dt.timedelta(days=8)))
        self.assertTrue(images.a_relire(images.mettre_a_jour(None, "cassee", "x", T), T))

    def test_remplacer_ligne_image(self):
        t = 'title: "A"\nimage: "https://x/a.jpg"\nlink: "https://x"\n'
        self.assertEqual(images.remplacer_image(t, "assets/images/a.jpg"),
                         'title: "A"\nimage: "assets/images/a.jpg"\nlink: "https://x"\n')

    def test_categories_illustrees(self):
        import yaml
        cats = yaml.safe_load((images.RACINE / "_data" / "categories.yml").read_text())
        for c in cats:
            self.assertTrue((images.RACINE / f"assets/categories/{c}.svg").is_file(), c)

    def test_illustrations_a_jour(self):
        """Les SVG du dépôt sont ceux que produit scrapers/illustrations.py (sinon : python3 -m scrapers.illustrations)."""
        import yaml
        from scrapers import illustrations
        cats = yaml.safe_load((images.RACINE / "_data" / "categories.yml").read_text())
        for cle, c in cats.items():
            self.assertEqual((images.RACINE / f"assets/categories/{cle}.svg").read_text(),
                             illustrations.svg(cle, c["label"], c["color"]), cle)

    def test_photo_du_club(self):
        """Le profil du club (fiches_clubs.json) sert de photo du lieu, avant Wikimedia Commons."""
        clubs = {"Calypso Club Hammamet": {"photo": "assets/clubs/calypso-club-hammamet/profil.jpg"}}
        with mock.patch("pathlib.Path.is_file", return_value=True):
            self.assertEqual(images.photo_du_lieu("Calypso Club Hammamet", {}, {}, clubs),
                             "assets/clubs/calypso-club-hammamet/profil.jpg")
        self.assertEqual(images.photo_du_lieu("Lieu inconnu", {}, {}, clubs), "")

    def _rep(self, code, type_, corps):
        r = mock.Mock(status_code=code, headers={"Content-Type": type_})
        r.iter_content.return_value = iter([corps])
        return r

    def test_recuperer(self):
        cas = [(200, "image/jpeg", b"\xff\xd8\xff", "ok"), (403, "text/html", b"", "cassee"),
               (200, "text/html", b"<html>", "cassee"), (200, "image/jpeg", b"<html>", "cassee"),
               (503, "text/html", b"", "incertaine")]
        for code, t, corps, attendu in cas:
            with mock.patch("requests.get", return_value=self._rep(code, t, corps)):
                self.assertEqual(images.recuperer("https://x/a.jpg")[0], attendu)

    def test_images_de_la_page(self):
        html = ('<meta property="og:image" content="/affiche.jpg"><script type="application/ld+json">'
                '{"@type":"Event","image":["https://x/b.png"]}</script>')
        r = mock.Mock(status_code=200, headers={"Content-Type": "text/html"}, text=html)
        with mock.patch("requests.get", return_value=r):
            self.assertEqual(images.images_de_la_page("https://x/e/1"), ["https://x/affiche.jpg", "https://x/b.png"])

    def test_passage_complet(self):
        """Image cassée → affiche de la page de l'annonce ; image qui marche → copie locale."""
        import pathlib, tempfile
        with tempfile.TemporaryDirectory() as d:
            racine = pathlib.Path(d)
            (racine / "_events").mkdir(); (racine / "_data").mkdir(); (racine / "assets/categories").mkdir(parents=True)
            (racine / "assets/categories/theatre.svg").write_text("<svg/>")
            (racine / "_events/a.md").write_text('---\ntitle: "A"\ncategory: "theatre"\nlink: "https://x/e/a"\nimage: "https://x/cassee.jpg"\n---\ntexte\n')
            (racine / "_events/b.md").write_text('---\ntitle: "B"\ncategory: "theatre"\nimage: "https://x/ok.jpg"\n---\n')
            (racine / "_events/c.md").write_text('---\ntitle: "C"\ncategory: "theatre"\nlink: "https://x/e/c"\nimage: "https://x/cassee2.jpg"\n---\n')

            def get(url, **kw):
                jpg = {"https://x/ok.jpg": b"\xff\xd8\xff-ok", "https://x/affiche.jpg": b"\xff\xd8\xff-affiche"}
                if url in jpg:
                    return self._rep(200, "image/jpeg", jpg[url])
                if url == "https://x/e/a":
                    return mock.Mock(status_code=200, headers={"Content-Type": "text/html"},
                                     text='<meta property="og:image" content="https://x/affiche.jpg">')
                return self._rep(404, "text/html", b"")

            with mock.patch.object(images, "RACINE", racine), mock.patch.object(images, "CACHE", racine / "_data/images.json"), \
                    mock.patch.object(images, "DOSSIER", racine / "assets/images"), mock.patch("requests.get", side_effect=get):
                images.main()
            a = (racine / "_events/a.md").read_text()
            self.assertIn('image: "assets/images/', a)
            self.assertEqual(next((racine / "assets/images").glob("*")).read_bytes()[:3], b"\xff\xd8\xff")
            self.assertIn('image: "assets/images/', (racine / "_events/b.md").read_text())
            self.assertIn('image: "assets/categories/theatre.svg"', (racine / "_events/c.md").read_text())


if __name__ == "__main__":
    unittest.main()
