# Skill — Récupération CFE impots.gouv.fr

Skill métier autonome pour un cabinet comptable.  
Automatise la connexion à l'espace professionnel impots.gouv.fr, la navigation vers les avis CFE et leur téléchargement.

## Installation

```bash
pip install -r skills/cfe_impots/requirements.txt
playwright install chromium
```

## Utilisation

```bash
# Lancement interactif (demande identifiant + mot de passe)
python -m skills.cfe_impots.cli

# Avec identifiant en argument (mot de passe demandé de façon sécurisée)
python -m skills.cfe_impots.cli --identifiant MON_IDENTIFIANT

# Choisir le répertoire de téléchargement
python -m skills.cfe_impots.cli --output /chemin/vers/dossier

# Consulter le journal d'expérience
python -m skills.cfe_impots.cli --status
```

## Architecture

| Fichier | Rôle |
|---|---|
| `navigator.py` | Navigateur Playwright : connexion, navigation, téléchargement |
| `experience_log.py` | Journal d'expérience persistant (`experience.json`) |
| `cli.py` | Interface ligne de commande |

## Journal d'expérience (`experience.json`)

Le skill apprend en continu :
- **Chemins de navigation validés** : mémorisés et rejoués en priorité à la prochaine exécution.
- **Sélecteurs CSS efficaces** : les sélecteurs qui ont fonctionné sont stockés par concept.
- **Variantes d'interface** : snapshots horodatés des pages rencontrées.
- **Historique des téléchargements** : SIRET, année, nom de fichier.
- **Erreurs et contournements** : pour éviter de reproduire les mêmes échecs.

## Sécurité

- Les identifiants ne sont **jamais stockés** dans le code ni dans le journal.
- Le mot de passe est saisi via `getpass` (non affiché, non loggué).
- Le skill n'effectue aucune action hors du périmètre CFE.
