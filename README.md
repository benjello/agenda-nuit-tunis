# ToNight Tunis : l'agenda de la nuit

Toutes les sorties de la nuit au même endroit, pour tous les publics : clubs, discothèques, cabarets,
concerts, bars et lounges, karaokés, stand-up, festivals et open air. Tunis d'abord, puis toute la Tunisie.
Publié avec GitHub Pages : https://benjello.github.io/agenda-nuit-tunis/

C'est le pendant nocturne de [l'agenda culturel de Tunis](https://github.com/benjello/agenda-culturel-tunis) :
même moteur (Jekyll, scrapers Python, GitHub Actions), mêmes formats. Seules changent les **sources**
(`_data/sources.yml`) et les **catégories** (`_data/categories.yml`). À l'écriture, chaque annonce reçoit sa
catégorie de nuit d'après son titre (« DJ set » → club, « karaoké » → karaoke, « dîner-spectacle » → cabaret) ;
les films, expos, conférences, ateliers et pièces de théâtre sont écartés (`scrapers/commun.py: categorie_nuit`).

**Catégories** : `club`, `discotheque`, `cabaret`, `concert`, `bar`, `karaoke`, `humour`, `festival`, `autre`.

## Ajouter un événement

Chaque événement est un petit fichier Markdown dans le dossier [`_events/`](_events/).

1. Sur GitHub, ouvrez le dossier `_events/` puis cliquez sur **Add file → Create new file**.
2. Nommez le fichier `AAAA-MM-JJ-nom-court.md`, par exemple `2026-11-07-concert-oud.md`.
3. Copiez ce modèle et remplissez-le :

```markdown
---
title: "Titre de l'événement"
date: 2026-11-07 20:30        # date et heure de début (AAAA-MM-JJ HH:MM)
end_date: 2026-11-30          # facultatif : date de fin (expos, festivals…)
venue: "Nom du lieu"
address: "Adresse, Tunis"     # facultatif
category: club                # voir la liste ci-dessus
price: "20 DT"                # facultatif
link: "https://…"             # page d'origine : Facebook, site du lieu, billetterie…
---
Une courte description de l'événement (facultatif).
```

4. Cliquez sur **Commit changes**. Le site se met à jour en une ou deux minutes.

**Catégories disponibles** : voir plus haut. Pour en ajouter une, modifiez
[`_data/categories.yml`](_data/categories.yml).

Les événements passés disparaissent automatiquement de la page d'accueil. Pas besoin de les supprimer.

**Par le formulaire** : [Proposer un événement](https://github.com/benjello/agenda-nuit-tunis/issues/new?template=evenement.yml).
Pour le publier, poser l'étiquette `valide` sur l'issue : le fichier est créé dans `_events/propositions/` et l'issue fermée.

Pensez d'abord à vérifier si le lieu peut devenir une **source** (voir plus bas) : c'est plus durable qu'une saisie à la main.

**Contributeurs extérieurs** : la page [Contribuer](https://benjello.github.io/agenda-nuit-tunis/contribuer/) liste les
sources recherchées (`_data/sources_recherchees.yml`, tenu à la main) et les sources à réparer (en pause, en panne,
silencieuses). Chaque bouton ouvre le formulaire « Proposer une source ». Les plus à l'aise ouvrent une pull request
sur `_data/sources.yml` ; le guide est dans [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md).

## Sources et scrapers (automatique)

L'agenda se remplit surtout tout seul : des **scrapers** relisent chaque jour des
**sources fiables** (sites de lieux, billetteries) et chaque événement renvoie vers sa source.

- La liste des sources est dans [`_data/sources.yml`](_data/sources.yml), visible sur la page
  [Sources](https://benjello.github.io/agenda-nuit-tunis/sources/) avec l'état de chacune.
- Chaque source indique quel scraper la lit (dossier [`scrapers/sources/`](scrapers/sources/)).
  Une source qui publie ses événements en schema.org s'ajoute avec `scraper: jsonld`, sans code.
- Les événements récupérés sont écrits en Markdown dans `_events/auto/<source>/`, comme ceux
  saisis à la main. Ne pas les modifier : le dossier est réécrit à chaque passage.
- **Un seul format pour tout** : chaque scraper produit des événements (`Evenement` dans
  `scrapers/commun.py`) : titre, début, fin, séances, lieu, adresse, catégorie, prix, lien, image.
  Un film à l'affiche est un événement de catégorie cinéma avec `film: true` et une séance par jour
  de projection. `scrapers/films.py` regroupe ensuite les salles de chaque film dans
  `_data/films.json` : le thème Cinéma montre un film (avec son affiche), puis les salles du jour choisi.
- **Ce qu'en dit la presse** : un article de journal sur un film en salles (critique, sortie) ne devient
  pas un événement (doublon des séances). Le scraper presse le garde dans `_data/critiques.json`
  (`scrapers/critiques.py`), et chaque film reçoit les articles qui le nomment : liens sur la fiche
  du film et encadré « Ce qu'en dit la presse » sur la page de chaque séance.
- Les programmes publiés en image (Facebook) sont gardés dans `_data/programmes/` et
  `assets/programmes/`, et les films qu'on y lit deviennent des événements.
- L'état de chaque source (dernier passage, succès, erreur) est noté dans `_data/etat_sources.json`.
- Si une source tombe en panne, ses événements déjà récupérés restent en place.
- **Granularité** : chaque entrée doit être un événement précis (un film avec ses séances, une expo avec ses
  dates, un lien vers sa propre fiche), pas une rubrique ni la page générale d'un institut. `scrapers/granularite.py`
  le vérifie après chaque passage ; la page « Santé des sources » montre, par source et par type de scraper,
  la part d'entrées précises et ce qui manque. Tests : `python3 -m unittest tests.test_granularite`.

### Lancer les scrapers

Sur GitHub : chaque jour vers 6h20, ou **Actions → Scrapers → Run workflow**.

Sur un ordinateur ou un serveur (par exemple dans un cron) :

```bash
pip install -r requirements.txt
python3 -m scrapers              # toutes les sources actives
python3 -m scrapers teskerti     # une seule source
python3 -m scrapers --debug      # garde les pages téléchargées dans debug/
git add _events/auto _data/films.json _data/programmes assets/programmes _data/etat_sources.json && git commit -m "Scrapers" && git push
```

Exemple de ligne cron (tous les jours à 6h) :
`0 6 * * * cd ~/agenda-nuit-tunis && git pull -q && python3 -m scrapers && git add -A _events/auto _data && git commit -qm Scrapers && git push -q`

Certains sites (pathe.tn par exemple) refusent les requêtes venant des serveurs de GitHub.
Ces sources marchent mieux depuis un cron sur une machine ordinaire.

### Ajouter une source sans écrire de code

Plusieurs scrapers sont génériques : une ligne dans `_data/sources.yml` suffit.

| Scraper | Pour une source qui… | Options |
|---|---|---|
| `rss` | publie un flux RSS/Atom d'événements (dates dans le titre ou le texte) | `lieu`, `nettoyer_titre` |
| `ical` | publie un calendrier `.ics` (agenda Google public, etc.) | `lieu` |
| `jsonld` | décrit ses événements en schema.org dans ses pages | aucune |
| `liste_fiches` | a une page de programme avec un lien vers une fiche par événement | `motif` (morceau d'adresse des fiches), `lieu` |
| `facebook` | annonce ses événements sur une page ou un groupe Facebook (voir ci-dessous) | `page`, `lieu`, `max` |

### Pages Facebook

Beaucoup de lieux de Tunis n'annoncent leur programme que sur Facebook. Facebook bloque les
robots, et son API ne donne les événements d'une page qu'à ses administrateurs. Le scraper
`facebook` passe donc par [Apify](https://apify.com), un service qui lit les événements
publics sans compte Facebook et les renvoie en JSON.

Pour l'activer, une seule fois :

1. Créer un compte gratuit sur apify.com (5 $ de crédit offerts chaque mois).
2. Copier la clé : **Settings → API & Integrations → Personal API token**.
3. Sur GitHub : **Settings → Secrets and variables → Actions → New repository secret**,
   nom `APIFY_TOKEN`, valeur la clé.

Sans clé, les sources Facebook sont « en attente » sur la page Sources et rien d'autre ne change.
Chaque événement lu coûte environ un centime : `tous_les_jours: 3` dans le registre limite la
fréquence. Ajouter une page = copier un bloc `scraper: facebook` et changer `page`.

Les scrapers `facebook_programmes` (pages Facebook) et `instagram` (comptes Instagram) lisent les
dernières **publications avec image** et le texte des affiches (OCR). Pour Instagram, chaque affiche
datée devient un événement (`compte`, `lieu` dans les options). Pour trouver des comptes :
**Actions → Recherche de sources Instagram → Run workflow**, avec des mots-clés.

Les sources repérées mais pas encore branchées sont dans le registre avec `actif: false`
(affichées « à étudier » sur la page Sources).

### Tests

`python3 -m unittest discover tests` vérifie les scrapers sur des pages d'exemple (`tests/fixtures/`).

## Données ouvertes

Le site publie `agenda.ics` (abonnement calendrier) et `evenements.json` (événements à venir),
générés à chaque construction. Licence des données : CC BY 4.0 (voir la page À propos).

## Organisation du dépôt

| Dossier / fichier | Rôle |
|---|---|
| `_events/` | un fichier par événement |
| `_events/auto/` | événements récupérés par les scrapers (généré) |
| `_data/sources.yml` | registre des sources |
| `_data/programmes/`, `assets/programmes/`, `_data/etat_sources.json` | programmes en image et état des sources (générés) |
| `scrapers/` | les scrapers (Python) |
| `tests/` | tests des scrapers |
| `_data/categories.yml` | catégories (nom affiché, couleur) |
| `_data/fr.yml` | noms des jours et des mois en français |
| `_layouts/`, `_includes/` | gabarits HTML des pages |
| `assets/style.css` | apparence du site |
| `index.html` | page d'accueil (l'agenda) |
| `a-propos.md` | page « À propos » |

## Voir le site sur son ordinateur (facultatif)

```bash
bundle install
bundle exec jekyll serve
```

Puis ouvrez http://localhost:4000/agenda-nuit-tunis/

## Prochaines étapes

Le suivi détaillé (état de chaque source, marche à suivre pour vérifier une nouvelle source) est dans [BACKLOG.md](BACKLOG.md).


- Formulaire de contribution (issue GitHub préremplie, ou Google Form) pour signaler un événement.
- Brancher les sources « à étudier » du registre.
- Contrôle de santé : alerte automatique quand une source meurt.
- Pages Facebook : lire aussi les publications (affiches) et en extraire les séances.
