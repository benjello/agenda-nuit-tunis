"""Illustrations de catégorie (assets/categories/<catégorie>.svg) : la vignette de remplacement
d'un événement dont l'image manque ou ne charge plus (voir scrapers/images.py et event-card.html).

Une par catégorie de _data/categories.yml : dégradé de la couleur de la catégorie vers le bleu nuit,
quelques étoiles, un pictogramme et le nom de la catégorie. Relancer après l'ajout d'une catégorie :

  python3 -m scrapers.illustrations
"""
from __future__ import annotations

from html import escape

import yaml

from .commun import RACINE

DOSSIER = RACINE / "assets" / "categories"
NUIT = "#0d0b1a"
TRAIT = 'fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"'

# Pictogrammes dessinés dans un carré de 120 × 150, centrés vers (60, 64).
PICTOS = {
    # disque vinyle
    "club": f'<g {TRAIT}><circle cx="60" cy="64" r="32"/><circle cx="60" cy="64" r="22" stroke-opacity=".5"/>'
            '<circle cx="60" cy="64" r="7"/><path d="M88 30l-14 22"/></g>',
    # boule à facettes
    "discotheque": f'<g {TRAIT}><path d="M60 18v14"/><circle cx="60" cy="64" r="30"/>'
                   '<path d="M30 64h60M34 49h52M34 79h52M60 34c-14 16-14 44 0 60M60 34c14 16 14 44 0 60"/></g>',
    # haut-de-forme et étoile
    "cabaret": f'<g {TRAIT}><path d="M40 42h40v34H40zM28 82h64"/><path d="M40 66h40"/></g>'
               '<path d="M86 28l3 7 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z" fill="#fff"/>',
    # micro sur pied
    "concert": f'<g {TRAIT}><rect x="50" y="30" width="20" height="34" rx="10"/><path d="M42 56c0 12 8 20 18 20s18-8 18-20M60 76v16M48 92h24"/></g>',
    # verre à cocktail
    "bar": f'<g {TRAIT}><path d="M34 36h52L60 66zM60 66v24M46 92h28M74 28l-8 14"/></g><circle cx="78" cy="26" r="5" fill="#fff"/>',
    # micro et note
    "karaoke": f'<g {TRAIT}><circle cx="50" cy="44" r="12"/><path d="M58 52l20 30"/></g>'
               f'<g {TRAIT}><path d="M84 36v22M84 36l10 4"/></g><circle cx="80" cy="60" r="5" fill="#fff"/>',
    # bulle de parole
    "humour": f'<g {TRAIT}><path d="M30 40h60v36H56l-14 12v-12H30z"/></g>'
              '<g fill="#fff"><circle cx="48" cy="58" r="4"/><circle cx="60" cy="58" r="4"/><circle cx="72" cy="58" r="4"/></g>',
    # mur d'enceintes
    "soundsystem": f'<g {TRAIT}><rect x="32" y="30" width="26" height="64" rx="3"/><rect x="62" y="30" width="26" height="64" rx="3"/>'
                   '<circle cx="45" cy="48" r="7"/><circle cx="45" cy="76" r="9"/><circle cx="75" cy="48" r="7"/><circle cx="75" cy="76" r="9"/></g>',
    # scène en plein air sous la lune
    "festival": f'<g {TRAIT}><path d="M24 92l22-30 14 16 12-12 24 26z"/><path d="M60 92V62"/></g>'
                '<path d="M84 26a12 12 0 1 0 8 20 10 10 0 1 1-8-20z" fill="#fff"/>',
}
# croissant de lune (autre soirée, et toute catégorie sans pictogramme)
LUNE = '<path d="M68 32a32 32 0 1 0 22 52 26 26 0 1 1-22-52z" fill="#fff" fill-opacity=".92"/>'
ETOILES = [(16, 18, 1.4), (100, 14, 1.1), (92, 104, 1.2), (22, 96, 1), (106, 64, .9), (12, 56, 1.1)]


def svg(cle: str, libelle: str, couleur: str) -> str:
    etoiles = "".join(f'<circle cx="{x}" cy="{y}" r="{r}"/>' for x, y, r in ETOILES)
    texte = escape(libelle.upper())
    taille = 11 if len(libelle) <= 14 else 9
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 150" role="img" aria-label="{escape(libelle)}">\n'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2=".6" y2="1"><stop offset="0" stop-color="{couleur}"/>'
        f'<stop offset="1" stop-color="{NUIT}"/></linearGradient></defs>\n'
        '<rect width="120" height="150" fill="url(#g)"/>\n'
        f'<g fill="#fff" fill-opacity=".7">{etoiles}</g>\n'
        f'{PICTOS.get(cle, LUNE)}\n'
        f'<text x="60" y="132" text-anchor="middle" font-family="sans-serif" font-size="{taille}" font-weight="700" '
        f'letter-spacing=".5" fill="#fff" fill-opacity=".92">{texte}</text>\n'
        '</svg>\n'
    )


def main() -> int:
    categories = yaml.safe_load((RACINE / "_data" / "categories.yml").read_text(encoding="utf-8"))
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for cle, c in categories.items():
        (DOSSIER / f"{cle}.svg").write_text(svg(cle, c["label"], c["color"]), encoding="utf-8")
    print(f"{len(categories)} illustrations dans {DOSSIER.relative_to(RACINE)}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
