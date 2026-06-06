#!/usr/bin/env bash
# Installation du skill CFE impots.gouv.fr
set -e

echo ""
echo "=== Installation du skill CFE impots.gouv.fr ==="
echo ""

# Python 3.9+ requis
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 non trouvé. Installez Python 3.9+ depuis https://python3.org"
  exit 1
fi

PY=$(python3 --version 2>&1)
echo "✓ $PY détecté"

# pip
if ! python3 -m pip --version &>/dev/null; then
  echo "❌ pip non trouvé. Lancez : python3 -m ensurepip --upgrade"
  exit 1
fi

# Installation Playwright
echo ""
echo "→ Installation de Playwright..."
python3 -m pip install --quiet playwright

# Installation Chromium
echo "→ Installation de Chromium (peut prendre 1-2 minutes)..."
python3 -m playwright install chromium

echo ""
echo "✅ Installation terminée."
echo ""
echo "=== Lancement du skill ==="
echo ""

# Demande identifiant
read -rp "Identifiant espace professionnel impots.gouv.fr : " IDENTIFIANT
if [ -z "$IDENTIFIANT" ]; then
  echo "❌ Identifiant requis."
  exit 1
fi

# Lancement depuis la racine du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"
python3 -m skills.cfe_impots.cli --identifiant "$IDENTIFIANT"
