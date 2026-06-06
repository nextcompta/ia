"""
Point d'entrée CLI du skill CFE impots.gouv.fr.

Usage :
    python -m skills.cfe_impots.cli [OPTIONS]

Options :
    --identifiant   Identifiant du portail professionnel (demandé si absent)
    --output        Répertoire de téléchargement (défaut : ./telechargements_cfe)
    --headless      Lance le navigateur sans interface graphique
    --status        Affiche le journal d'expérience et quitte
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from . import experience_log as log
from .navigator import CFENavigator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cfe_impots",
        description="Skill CFE — Récupération des avis CFE depuis impots.gouv.fr",
    )
    p.add_argument("--identifiant", default="", help="Identifiant espace professionnel")
    p.add_argument(
        "--output", default="./telechargements_cfe",
        help="Répertoire de destination des téléchargements",
    )
    p.add_argument(
        "--headless", action="store_true",
        help="Navigateur sans interface graphique (déconseillé sur impots.gouv.fr)",
    )
    p.add_argument("--status", action="store_true", help="Afficher le journal d'expérience")
    return p.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    if args.status:
        import json
        print(json.dumps(log.summary(), ensure_ascii=False, indent=2))
        return 0

    identifiant = args.identifiant or input("Identifiant espace professionnel : ").strip()
    if not identifiant:
        print("[CFE] Identifiant requis.", file=sys.stderr)
        return 1

    mot_de_passe = getpass.getpass("Mot de passe : ")
    if not mot_de_passe:
        print("[CFE] Mot de passe requis.", file=sys.stderr)
        return 1

    nav = CFENavigator(download_dir=args.output, headless=args.headless)
    files = await nav.run(identifiant=identifiant, mot_de_passe=mot_de_passe)

    if files:
        print(f"\n[CFE] {len(files)} fichier(s) téléchargé(s) :")
        for f in files:
            print(f"  {f}")
    else:
        print("[CFE] Aucun fichier téléchargé.")

    return 0 if files else 1


def main() -> None:
    args = parse_args()
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
