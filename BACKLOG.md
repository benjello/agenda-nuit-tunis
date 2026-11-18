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

- #2 Tri des comptes repérés par les hashtags (rouvert chaque lundi par `scrapers/tri_comptes.py`)
- #3 Brancher les clubs de Gammarth, La Marsa, Hammamet, Sousse et Monastir
- #4 Brancher cabarets, bars à programmation, karaokés et scènes de stand-up
- #5 Filtre « Public » sur l'accueil
- #6 Compléter les soirées de chaque semaine (`_data/recurrentes.yml`)


## Fait (18 novembre 2026)

- [x] Suivi automatique : une issue « Source en panne : <id> » par source en échec deux passages de suite,
      mise à jour et fermée par le workflow des scrapers (`scrapers/suivi.py`) ; les alertes (étiquette `alerte`)
      sortent de la synchro du backlog. Une tâche Claude, chaque soir, relit les alertes, propose les correctifs
      clairs en PR (fusionnés seuls si tests verts, pour une correction ciblée de source) et envoie un résumé.
- [x] Instagram : « Ce jeudi : live de ZANZANA », « ce soir », « demain » donnent la date quand l'affiche n'en donne pas
      (Rock'n'Rolla : 2 soirées comprises sur 6 publications avant, 6 sur 6 après) ; le titre ne garde plus
      « Dimanche 15 Novembre » ni le « avec » d'un compte cité (`scrapers/lecteurs.py`).
- [x] Teskerti : la rubrique « Clubbing » restait sur une soirée passée et « Spectacle » se charge en JavaScript ;
      l'accueil, rangé par rubrique, complète la liste (`scrapers/sources/teskerti.py: liens_accueil`).
- [x] Soirées de chaque semaine : `_data/recurrentes.yml` (scraper `recurrentes`), publiées deux semaines à l'avance,
      retirées sans preuve depuis 60 jours.
- [x] Sources silencieuses : alerte après 14 jours sans annonce (30 avant).
- [x] Une soirée qui finit après minuit reste dans « Ce soir » jusqu'à sa fin : jusqu'à 6 h, l'agenda montre encore
      la nuit de la veille.
- [x] Champs de la nuit lus dans l'annonce (`scrapers/commun.py: infos_nuit`, posés par `scrapers/ranger.py`) :
      âge minimum, dress code, entrée sur liste, tarif avant / après minuit, numéro de réservation.
      Une valeur saisie à la main dans `_events/` n'est pas remplacée.
- [x] Filtre « À quelle heure » : début de soirée (17 h – 23 h), nuit (23 h – 3 h), after.
- [x] Boutons « Réserver » (appel ou WhatsApp : numéro de l'annonce, sinon celui du lieu) et « Partager sur WhatsApp ».
- [x] Fiches lieux : téléphone, horaires et site repris de la liste OpenStreetMap des clubs et bars, quand le nom
      est le même (`scrapers/pages.py: club_osm`) ; adresse visible aussi sur téléphone.
- [x] Clé `APIFY_TOKEN` : configurée dans les secrets du dépôt (crédit suivi chaque jour, alerte à 80 %).

## Fait (8 novembre 2026)

- [x] Premier tri des comptes repérés par les hashtags (#1) : 14 faux positifs écartés, NF Event branché, bars à sport filtrés, lieux cités par les artistes. Un nouveau ticket « tri-comptes » est ouvert chaque lundi s'il n'y en a pas (`scrapers/tri_comptes.py`), hors synchro du backlog.

- [x] Reprise du moteur de l'agenda culturel (Jekyll, scrapers, page Sources, carte, ICS, API), données culturelles vidées.
- [x] Catégories de la nuit (`_data/categories.yml`) : club, discothèque, cabaret, concert live, bar & lounge, sound system,
      karaoké, stand-up, festival & open air, autre soirée.
- [x] Tri à l'écriture (`scrapers/commun.py: categorie_nuit`) : le titre donne la catégorie (« DJ » → club,
      « karaoké » → karaoke…) ; films, expos, conférences, ateliers et pièces de théâtre sont écartés.
- [x] Sources de départ : Resident Advisor, tunis.events (rubriques nightlife, concerts, stand-up), Teskerti
      (clubbing, concerts, humour), l'agenda du jour de Tunisie Numérique, et les clubs, collectifs et DJ déjà
      suivis par l'agenda culturel (Habibi Downtown, Downtown Vibes, Rock'n'Rolla, Steppers, Fabrika…).

## À faire

- [ ] #3 Brancher les clubs et discothèques de Gammarth, La Marsa, Hammamet, Sousse et Monastir (comptes Instagram),
      voir `_data/sources_recherchees.yml`.
- [ ] #4 Brancher les cabarets et dîners-spectacles, les bars à programmation, les karaokés et les scènes de stand-up.
- [ ] #5 Filtre « Public » sur l'accueil : étudiants, 25 ans et plus, famille (day parties, cabarets), entrée gratuite.
- [ ] #6 Noter les rendez-vous fixes des lieux suivis dans `_data/recurrentes.yml` (live, karaoké, open mic…).

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

