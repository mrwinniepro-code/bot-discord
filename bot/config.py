"""Configuration centrale : lecture du .env, chemins, URL de base de donnees."""
from __future__ import annotations

import os
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
