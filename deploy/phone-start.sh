#!/usr/bin/env bash
# ============================================================================
#  Lance le bot en continu sur un telephone Android (Termux).
#   - termux-wake-lock : empeche Android d'endormir/tuer le bot ecran eteint
#   - boucle while     : redemarre automatiquement le bot s'il plante
#   - Ctrl+C           : arrete proprement (ne redemarre PAS)
#
#  Utilisation :  bash deploy/phone-start.sh
# ============================================================================
cd "$(dirname "$0")/.." || exit 1

# Ctrl+C -> on libere le wake-lock et on sort completement de la boucle
trap 'echo; echo "== Bot arrete. =="; termux-wake-unlock 2>/dev/null; exit 0' INT TERM

termux-wake-lock 2>/dev/null || true

echo "== Bot lance en mode 24/7. Garde Termux ouvert (ecran eteint OK). =="
echo "== Appuie sur Ctrl+C pour arreter. =="

while true; do
    python run_bot.py
    code=$?
    # 130 = arret volontaire via Ctrl+C -> on ne redemarre pas
    if [ "$code" -eq 130 ]; then
        echo "== Bot arrete. =="
        termux-wake-unlock 2>/dev/null || true
        break
    fi
    echo "[$(date '+%H:%M:%S')] Bot arrete (code $code), redemarrage dans 5s..."
    sleep 5
done
