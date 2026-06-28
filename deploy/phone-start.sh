#!/usr/bin/env bash
# ============================================================================
#  Lance le bot en continu sur un telephone Android (Termux).
#   - termux-wake-lock : empeche Android d'endormir/tuer le bot ecran eteint
#   - boucle while     : redemarre automatiquement le bot s'il s'arrete
#
#  Utilisation :  bash deploy/phone-start.sh
#  Pour arreter : Ctrl+C
# ============================================================================
cd "$(dirname "$0")/.." || exit 1

# Empeche la mise en veille (ignore l'erreur si la commande n'existe pas)
termux-wake-lock 2>/dev/null || true

echo "== Bot lance en mode 24/7. Garde Termux ouvert (ecran eteint OK). =="
echo "== Ctrl+C pour arreter. =="

while true; do
    python run_bot.py
    echo "[$(date '+%H:%M:%S')] Bot arrete, redemarrage dans 5s..."
    sleep 5
done
