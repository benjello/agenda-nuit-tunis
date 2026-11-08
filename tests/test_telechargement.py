import unittest
from unittest import mock

import requests

from scrapers import commun


class Reessai(unittest.TestCase):
    def test_reessaie_apres_un_delai_depasse(self):
        reponse = mock.Mock(encoding="utf-8", text="ok")
        with mock.patch.object(commun._session, "get",
                               side_effect=[requests.exceptions.Timeout("lent"), reponse]) as get, \
             mock.patch.object(commun.time, "sleep") as sommeil:
            self.assertEqual(commun.telecharger("https://exemple.tn/"), "ok")
        self.assertEqual(get.call_count, 2)
        sommeil.assert_called_once_with(2)

    def test_abandonne_apres_trois_essais(self):
        with mock.patch.object(commun._session, "get",
                               side_effect=requests.exceptions.ConnectionError("coupé")) as get, \
             mock.patch.object(commun.time, "sleep"):
            with self.assertRaises(requests.exceptions.ConnectionError):
                commun.telecharger("https://exemple.tn/")
        self.assertEqual(get.call_count, 3)

    def test_erreur_http_non_reessayee(self):
        reponse = mock.Mock(encoding="utf-8", text="")
        reponse.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        with mock.patch.object(commun._session, "get", return_value=reponse) as get:
            with self.assertRaises(requests.exceptions.HTTPError):
                commun.telecharger("https://exemple.tn/")
        self.assertEqual(get.call_count, 1)


if __name__ == "__main__":
    unittest.main()
