# Backlog de ToNight Tunis (l'agenda de la nuit)

Ce fichier garde la trace de ce qui est fait, de ce qui reste à faire, et de la marche à suivre
pour vérifier chaque nouvelle source. À mettre à jour à chaque changement.

État en direct de chaque source : page [Sources](https://benjello.github.io/agenda-nuit-tunis/sources/).

Même moteur que [l'agenda culturel](https://github.com/benjello/agenda-culturel-tunis) : une amélioration
du moteur (scrapers, pages) se fait d'abord là-bas, puis se reporte ici.

## Tickets ouverts

Les points restants sont suivis en issues GitHub : [liste des issues](https://github.com/benjello/agenda-nuit-tunis/issues).
Chaque lundi, le workflow « Synchro tickets » compare les cases non cochées de ce fichier aux issues ouvertes
(`scrapers/synchro_tickets.py`) et signale les écarts dans son résumé.

## Fait (8 novembre 2026)

- [x] Reprise du moteur de l'agenda culturel (Jekyll, scrapers, page Sources, carte, ICS, API), données culturelles vidées.
- [x] Catégories de la nuit (`_data/categories.yml`) : club, discothèque, cabaret, concert live, bar & lounge,
      karaoké, stand-up, festival & open air, autre soirée.
- [x] Tri à l'écriture (`scrapers/commun.py: categorie_nuit`) : le titre donne la catégorie (« DJ » → club,
      « karaoké » → karaoke…) ; films, expos, conférences, ateliers et pièces de théâtre sont écartés.
- [x] Sources de départ : Resident Advisor, tunis.events (rubriques nightlife, concerts, stand-up), Teskerti
      (clubbing, concerts, humour), l'agenda du jour de Tunisie Numérique, et les clubs, collectifs et DJ déjà
      suivis par l'agenda culturel (Habibi Downtown, Downtown Vibes, Rock'n'Rolla, Steppers, Fabrika…).

## À faire

- [ ] Brancher les clubs et discothèques de Gammarth, La Marsa, Hammamet, Sousse et Monastir (comptes Instagram),
      voir `_data/sources_recherchees.yml`.
- [ ] Brancher les cabarets et dîners-spectacles, les bars à programmation, les karaokés et les scènes de stand-up.
- [ ] Champs propres à la nuit sur chaque fiche : âge minimum, tarif avant / après minuit, dress code, entrée sur liste.
- [ ] Filtre « Public » sur l'accueil : étudiants, 25 ans et plus, famille (day parties, cabarets), entrée gratuite.
- [ ] Filtre par heure : début de soirée (avant 23 h), nuit, after.
- [ ] Une soirée qui finit après minuit reste dans « Ce soir » jusqu'à sa fin (aujourd'hui elle passe au lendemain à minuit).
- [ ] Clé `APIFY_TOKEN` dans les secrets du dépôt (lecture Instagram et Facebook) : même compte que l'agenda culturel
      ou un compte à part ? À décider avec Mahdi.

## Vérifier une nouvelle source (à refaire pour chaque entrée)

0. **Chercher aussi la page Facebook** (et Instagram) du lieu : à Tunis, c'est souvent là que
   l'information à jour se trouve. Une page Facebook se branche avec `scraper: facebook_programmes`
   (dernières publications avec image + OCR), et un lecteur si le programme a un format récurrent.
1. **Ajouter la source** dans [`_data/sources.yml`](_data/sources.yml) : `id`, `nom`, `url`, `type`,
   `scraper`, `categorie`, `actif: true`. Un scraper générique suffit souvent (voir le README).
2. **La lancer seule** : GitHub → Actions → Scrapers → Run workflow, et mettre son `id` dans
   le champ « sources ». Sur un ordinateur : `python3 -m scrapers <id> --debug`.
3. **Lire le journal** de l'exécution : la ligne `✓ <id> : N` donne le nombre d'événements,
   `✗ <id> : …` l'erreur.
4. **Contrôler 2 ou 3 événements** sur le site : titre, date et heure, lieu, lien vers la source.
5. **Vérifier les doublons** : un événement déjà vu ailleurs (même lieu, même heure) doit
   apparaître une seule fois, avec « Aussi sur : … ».
6. **Ajouter un test** avec une page d'exemple dans `tests/fixtures/` si le scraper est nouveau.

