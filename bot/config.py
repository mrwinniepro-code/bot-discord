"""Configuration centrale : lecture du .env, chemins, URL de base de donnees."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

# Racine du projet (le dossier qui contient ce package "bot")
BASE_DIR = Path(__file__).resolve().parent.parent

# Charge les variables depuis le fichier .env a la racine
load_dotenv(BASE_DIR / ".env")

# --- Dossiers de donnees ---
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = DATA_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"

for _d in (DATA_DIR, ASSETS_DIR, FONTS_DIR, BACKGROUNDS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --- Variables d'environnement ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()

DEV_GUILD_ID = os.getenv("DEV_GUILD_ID", "").strip() or None

# Par defaut : SQLite dans data/config.db. Surchargé par DATABASE_URL si présent.
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or (
    "sqlite:///" + (DATA_DIR / "config.db").as_posix()
)

# --- Dashboard web (Phase 2) ---
# Identifiants OAuth2 de l'application Discord (memes que le bot).
DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "").strip()

# URL publique du dashboard (sans / final). En local : http://localhost:5000
DASHBOARD_BASE_URL = os.getenv("DASHBOARD_BASE_URL", "http://localhost:5000").strip().rstrip("/")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))

# Cle secrete pour signer les sessions Flask. Si absente, on en genere une
# (les sessions seront alors invalidees a chaque redemarrage).
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "").strip() or secrets.token_hex(32)
