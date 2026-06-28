#!/data/data/com.termux/files/usr/bin/sh
# ============================================================================
#  Demarre automatiquement le bot au demarrage du telephone (via Termux:Boot).
#  A copier dans ~/.termux/boot/ (voir deploy/DEPLOY.md).
# ============================================================================
termux-wake-lock
cd ~/bot-discord || exit 1
exec bash deploy/phone-start.sh
