"""Référencement : plan du site et balises indispensables dans la mise en page.

  python3 -m unittest tests.test_referencement -v
"""
import unittest

from scrapers.commun import RACINE


class TestReferencement(unittest.TestCase):
    def test_plugin_sitemap_active(self):
        config = (RACINE / "_config.yml").read_text(encoding="utf-8")
        self.assertIn("jekyll-sitemap", config)

    def test_balises_dans_la_mise_en_page(self):
        mise_en_page = (RACINE / "_layouts" / "default.html").read_text(encoding="utf-8")
        for balise in ('rel="canonical"', 'property="og:url"', 'property="og:description"',
                       'name="twitter:card"', 'property="og:image"'):
            self.assertIn(balise, mise_en_page)

    def test_donnees_structurees(self):
        self.assertIn("application/ld+json", (RACINE / "_layouts" / "event.html").read_text(encoding="utf-8"))
        self.assertIn('"WebSite"', (RACINE / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
