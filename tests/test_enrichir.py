"""Fiches plus riches : prix des billetteries, langue, photos Wikidata, infos OpenStreetMap (hors ligne)."""
import unittest


class Prix(unittest.TestCase):
    def test_offre(self):
        from scrapers.sources.jsonld import prix_offre
        self.assertEqual(prix_offre({"price": 0}), "Gratuit")
        self.assertEqual(prix_offre({"price": "20", "priceCurrency": "TND"}), "20 TND")
        self.assertEqual(prix_offre({"price": "20", "priceCurrency": "TND", "availability": "https://schema.org/SoldOut"}),
                         "20 TND · Complet")
        self.assertEqual(prix_offre({"availability": "SoldOut"}), "Complet")
        self.assertEqual(prix_offre({}), "")


class Langue(unittest.TestCase):
    def test_langues(self):
        from scrapers.commun import langues_annoncees as l
        self.assertEqual(l("Philo-Art pour enfants en français"), ["fr"])
        self.assertEqual(l("Hamlet", "Une pièce en arabe tunisien, surtitrée."), ["ar"])
        self.assertEqual(l("Le Temps suspendu", "Projection en VOSTFR."), ["vo"])
        self.assertEqual(l("Foire du livre : traduire le savoir en arabe"), [])
        self.assertEqual(l("Concert de jazz"), [])


class Enrichir(unittest.TestCase):
    def test_wikidata_homonymes(self):
        from scrapers.enrichir import acceptable
        def e(**claims):
            return {"claims": {p: [{"mainsnak": {"datavalue": {"value": {"id": v}}}}] for p, v in claims.items()}}
        self.assertTrue(acceptable(e(P31="Q5", P27="Q948"), "artiste"))
        self.assertFalse(acceptable(e(P31="Q5", P27="Q142"), "artiste"))   # homonyme français
        self.assertTrue(acceptable(e(P17="Q948"), "lieu"))
        self.assertFalse(acceptable(e(P17="Q142"), "lieu"))

    def test_commons(self):
        from scrapers.enrichir import commons
        c = commons("Théâtre municipal de Tunis.jpg")
        self.assertIn("Special:FilePath/Théâtre_municipal_de_Tunis.jpg", c["image"])
        self.assertIn("File:Théâtre_municipal_de_Tunis.jpg", c["credit"])

    def test_osm(self):
        from scrapers.enrichir import chercher_osm, osm_index
        index = osm_index([
            {"tags": {"name": "Théâtre Municipal de Tunis", "wheelchair": "limited"}},
            {"tags": {"name": "Musée national du Bardo", "opening_hours": "Tu-Su 09:30-16:30"}},
            {"tags": {"name": "Sans info"}},
        ])
        self.assertEqual(chercher_osm(index, "Théâtre municipal de Tunis"), {"wheelchair": "limited"})
        self.assertEqual(chercher_osm(index, "Musée National du Bardo")["opening_hours"], "Tu-Su 09:30-16:30")
        self.assertIsNone(chercher_osm(index, "Sans info"))
        self.assertIsNone(chercher_osm(index, "El Teatro"))


if __name__ == "__main__":
    unittest.main()
