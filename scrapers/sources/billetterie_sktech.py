"""Billetteries en ligne faites par SK TECH : El Teatro et Théâtre de l'Opéra de Tunis.

Les deux sites ont la même structure :
  /fr/programmes            liste des spectacles
  /fr/programme/<nom>       un spectacle, avec un tableau des séances
                            (« 07 Novembre 2026 à 19:30 »)

C'est un cas particulier du scraper générique liste_fiches.
Options :
  lieu : nom du lieu affiché (les fiches ne le répètent pas toujours)
"""
from . import liste_fiches


def recuperer(source: dict):
    return liste_fiches.recuperer(source, motif_defaut="/fr/programme/")
