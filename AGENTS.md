# Consignes pour les agents (Claude et autres)

ToNight Tunis, l'agenda de la nuit (clubs, discothèques, cabarets, concerts, stand-up). Même moteur que benjello/agenda-culturel-tunis : site Jekyll sur GitHub Pages, scrapers Python lancés chaque jour par
GitHub Actions (`.github/workflows/scrapers.yml`). Voir `README.md` et `BACKLOG.md` (à tenir à jour).

## Données : d'abord les sources ouvertes

- **Chercher d'abord dans Wikidata** (CC0) et Wikipédia, puis les autres sources ouvertes
  (OpenStreetMap / Nominatim, flux RSS, iCal, schema.org des pages) avant toute API à clé
  ou tout site qui interdit la copie (IMDb, par exemple).
- Modules existants à réutiliser : `scrapers/wikidata.py` (films : IMDb, genres, âge, film tunisien),
  `scrapers/descriptifs.py` (Wikipédia via Wikidata pour lieux, festivals, musées, films),
  `scrapers/pages.py` (coordonnées OpenStreetMap).
- Garder les réponses en cache dans `_data/*.json` pour ne pas réinterroger chaque jour,
  et citer la source (lien) à l'affichage ; Wikipédia est sous CC BY-SA.
- Outils gratuits uniquement ; une clé payante ou une inscription lourde se décide avec Mahdi
  (noter la question dans `BACKLOG.md`).

## Façon de travailler

- Tout en français (code, commentaires, messages de commit, textes du site).
- Tout ce qui peut être scripté l'est (GitHub Actions), pour ne pas dépendre d'un agent.
- Tests hors ligne : `python3 -m unittest discover tests` (pages d'exemple dans `tests/fixtures/`).
- Tickets et backlog alignés : chaque point ouvert est une case non cochée dans `BACKLOG.md` **et**
  une issue GitHub (listée dans sa section « Tickets ouverts »). Une PR qui traite une issue écrit
  « Closes #N » ; une issue ne se ferme qu'une fois sa case cochée. Le workflow « Synchro tickets »
  (chaque lundi) lance `scrapers/synchro_tickets.py` et signale les écarts dans son résumé.
