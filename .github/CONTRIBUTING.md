# Contribuer à ToNight Tunis, l'agenda de la nuit

Merci ! Le plus utile : **trouver les pages où les lieux annoncent leurs dates**.
La liste de ce qu'on cherche est sur la page [Contribuer](https://benjello.github.io/agenda-nuit-tunis/contribuer/).

## Sans rien installer (le plus simple)

- **Donner une adresse** : formulaire « Proposer une source » (une issue GitHub). On la branche nous-mêmes.
- **Ajouter la source vous-même** : ouvrez [`_data/sources.yml`](../_data/sources.yml) sur GitHub, cliquez
  sur le crayon ✎, ajoutez une entrée à la fin, puis « Propose changes ». GitHub crée la copie (fork)
  et la pull request pour vous.

Modèle pour une page Facebook :

```yaml
- id: fb-maison-culture-ibn-khaldoun     # court, unique, en minuscules avec des tirets
  nom: Maison de la culture Ibn Khaldoun
  url: https://www.facebook.com/…
  type: lieu
  genre: lieu                            # lieu | institution | festival | collectif | administration | presse | agenda
  scraper: facebook_programmes           # instagram pour un compte Instagram, rss pour un flux
  categorie: autre                       # voir _data/categories.yml
  actif: true
  tous_les_jours: 3
  options:
    page: nom-de-la-page                 # ce qui suit facebook.com/
    lieu: "Maison de la culture Ibn Khaldoun"
  note: "Une phrase pour dire ce qu'on y trouve."
```

Copiez une entrée voisine du même `scraper` dans le fichier : les `options` en dépendent.
Une fois la source branchée, retirez-la de [`_data/sources_recherchees.yml`](../_data/sources_recherchees.yml).

## Ce qui est vérifié automatiquement

À chaque pull request, GitHub relance les tests (`python3 -m unittest discover tests`), dont la
vérification du registre des sources (identifiant unique, scraper qui existe, catégorie connue, adresse
en `https://`). Un résumé indique aussi si la PR touche au code ou aux workflows, ce qui demande une
relecture plus longue.

## Règles

- Sources publiques uniquement (visibles sans se connecter), soirées et sorties de nuit en Tunisie
  (les autres villes sont acceptées, rangées à part).
- Pas de publicité, pas de liens sans rapport : ces PR et issues sont fermées sans réponse.
- Tout en français (code, commentaires, messages de commit).
- Une PR = un sujet. Une petite PR de données est relue en quelques jours.
