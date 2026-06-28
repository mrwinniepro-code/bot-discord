#!/usr/bin/env bash
# ============================================================================
#  Installation automatique du bot + dashboard sur un serveur Ubuntu (Oracle).
#
#  A lancer depuis le dossier du projet, en passant ton domaine en argument :
#      bash deploy/setup.sh  mondomaine.duckdns.org
#
#  Pré-requis : le fichier .env doit déjà exister et être rempli.
# ============================================================================
set -e

DOMAIN="${1:-}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUN_USER="$(whoami)"
VENV="$PROJECT_DIR/.venv"
PY="$VENV/bin/python"

echo "=================================================================="
echo " Projet      : $PROJECT_DIR"
echo " Utilisateur : $RUN_USER"
echo " Domaine     : ${DOMAIN:-<aucun : HTTPS non configuré>}"
echo "=================================================================="

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "ERREUR : le fichier .env est introuvable. Crée-le avant de lancer ce script."
  exit 1
fi

# --- 1) Paquets système -----------------------------------------------------
echo "[1/7] Installation des paquets système..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git curl openssl \
  debian-keyring debian-archive-keyring apt-transport-https iptables-persistent

# --- 2) Caddy (serveur web + HTTPS automatique) -----------------------------
if ! command -v caddy >/dev/null 2>&1; then
  echo "[2/7] Installation de Caddy..."
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y caddy
else
  echo "[2/7] Caddy déjà installé."
fi

# --- 3) Environnement Python ------------------------------------------------
echo "[3/7] Création de l'environnement Python et installation des dépendances..."
python3 -m venv "$VENV"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install -r "$PROJECT_DIR/requirements.txt" gunicorn

# --- 4) Clé secrète Flask (sessions) ---------------------------------------
if ! grep -q '^FLASK_SECRET_KEY=.\+' "$PROJECT_DIR/.env"; then
  echo "[4/7] Génération d'une clé secrète Flask..."
  KEY="$(openssl rand -hex 32)"
  sed -i '/^FLASK_SECRET_KEY=/d' "$PROJECT_DIR/.env"
  echo "FLASK_SECRET_KEY=$KEY" >> "$PROJECT_DIR/.env"
else
  echo "[4/7] Clé secrète Flask déjà présente."
fi

# --- 5) Ouverture des ports 80 / 443 (pare-feu local Ubuntu) ----------------
echo "[5/7] Ouverture des ports 80 et 443..."
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT || true
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT || true
sudo netfilter-persistent save || true

# --- 6) Services systemd (démarrage auto + redémarrage auto) ----------------
echo "[6/7] Installation des services systemd..."
sudo tee /etc/systemd/system/chadbot.service >/dev/null <<EOF
[Unit]
Description=ChadBot (bot Discord)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PY run_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/chadbot-dashboard.service >/dev/null <<EOF
[Unit]
Description=ChadBot dashboard (web)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 "dashboard.app:create_app()"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# --- 7) Caddy : reverse proxy + HTTPS ---------------------------------------
if [ -n "$DOMAIN" ]; then
  echo "[7/7] Configuration de Caddy pour $DOMAIN..."
  sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$DOMAIN {
    reverse_proxy 127.0.0.1:5000
}
EOF
  sudo systemctl restart caddy
else
  echo "[7/7] Pas de domaine fourni : Caddy non configuré (HTTPS désactivé)."
fi

# --- Démarrage --------------------------------------------------------------
sudo systemctl daemon-reload
sudo systemctl enable chadbot.service chadbot-dashboard.service
sudo systemctl restart chadbot.service chadbot-dashboard.service

echo ""
echo "=================================================================="
echo " Terminé ! État des services :"
echo "=================================================================="
sleep 2
sudo systemctl --no-pager --lines=8 status chadbot.service || true
sudo systemctl --no-pager --lines=8 status chadbot-dashboard.service || true
echo ""
echo "Le bot devrait être en ligne sur Discord."
if [ -n "$DOMAIN" ]; then
  echo "Le dashboard sera accessible sur : https://$DOMAIN"
  echo "(le certificat HTTPS peut prendre 1 à 2 minutes à s'activer)"
fi
