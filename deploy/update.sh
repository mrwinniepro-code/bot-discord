#!/usr/bin/env bash
# Met à jour le bot depuis GitHub puis redémarre les services.
#   bash deploy/update.sh
set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
git pull
"$PROJECT_DIR/.venv/bin/pip" install -r requirements.txt gunicorn
sudo systemctl restart chadbot.service chadbot-dashboard.service
echo "Mise à jour terminée."
sudo systemctl --no-pager --lines=5 status chadbot.service || true
