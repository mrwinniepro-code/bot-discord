"""Appels a l'API Discord pour le dashboard (OAuth2 + lecture serveurs/salons/roles)."""
from __future__ import annotations

import time
from urllib.parse import urlencode

import requests

from bot.config import (
    DASHBOARD_BASE_URL,
    DISCORD_CLIENT_ID,
    DISCORD_CLIENT_SECRET,
    DISCORD_TOKEN,
)

API = "https://discord.com/api/v10"
REDIRECT_URI = f"{DASHBOARD_BASE_URL}/callback"
OAUTH_SCOPE = "identify guilds"

# Permissions Discord (bitmask)
PERM_ADMINISTRATOR = 0x8
PERM_MANAGE_GUILD = 0x20

# Types de salons "textuels" ou poster les messages
TEXT_CHANNEL_TYPES = {0, 5}  # 0 = texte, 5 = annonces


# Permissions demandees a l'invitation du bot (Voir/Envoyer/Embed/Fichiers,
# Gerer roles/salons/messages, Kick/Ban/Timeout, Reactions, Historique)
INVITE_PERMISSIONS = (
    0x400 | 0x800 | 0x4000 | 0x8000 | 0x10000 | 0x40
    | 0x10000000 | 0x10 | 0x2 | 0x4 | 0x2000 | 0x10000000000
)


def invite_url(guild_id: str | None = None) -> str:
    """Lien pour inviter le bot (eventuellement sur un serveur precis)."""
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "scope": "bot applications.commands",
        "permissions": INVITE_PERMISSIONS,
    }
    if guild_id:
        params["guild_id"] = guild_id
        params["disable_guild_select"] = "true"
    return "https://discord.com/oauth2/authorize?" + urlencode(params)


def authorize_url(state: str) -> str:
    """URL vers laquelle rediriger l'utilisateur pour se connecter avec Discord."""
    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": OAUTH_SCOPE,
        "state": state,
        "prompt": "consent",
    }
    return "https://discord.com/oauth2/authorize?" + urlencode(params)


def exchange_code(code: str) -> dict:
    """Echange le code OAuth contre un token d'acces utilisateur."""
    data = {
        "client_id": DISCORD_CLIENT_ID,
        "client_secret": DISCORD_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    r = requests.post(
        f"{API}/oauth2/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _bot() -> dict:
    return {"Authorization": f"Bot {DISCORD_TOKEN}"}


def get_user(token: str) -> dict:
    r = requests.get(f"{API}/users/@me", headers=_bearer(token), timeout=15)
    r.raise_for_status()
    return r.json()


def get_user_guilds(token: str) -> list[dict]:
    r = requests.get(f"{API}/users/@me/guilds", headers=_bearer(token), timeout=15)
    r.raise_for_status()
    return r.json()


_bot_guilds_cache: dict = {"ts": 0.0, "ids": set()}


def get_bot_guild_ids() -> set[str]:
    """IDs des serveurs ou le bot est present (cache 30s)."""
    now = time.time()
    if now - _bot_guilds_cache["ts"] < 30 and _bot_guilds_cache["ids"]:
        return _bot_guilds_cache["ids"]
    r = requests.get(f"{API}/users/@me/guilds", headers=_bot(), timeout=15)
    r.raise_for_status()
    ids = {g["id"] for g in r.json()}
    _bot_guilds_cache.update(ts=now, ids=ids)
    return ids


def get_guild_channels(guild_id: str) -> list[dict]:
    r = requests.get(f"{API}/guilds/{guild_id}/channels", headers=_bot(), timeout=15)
    r.raise_for_status()
    return r.json()


def get_guild_roles(guild_id: str) -> list[dict]:
    r = requests.get(f"{API}/guilds/{guild_id}/roles", headers=_bot(), timeout=15)
    r.raise_for_status()
    return r.json()


def text_channels(guild_id: str) -> list[dict]:
    """Salons textuels, tries par position."""
    chans = [c for c in get_guild_channels(guild_id) if c.get("type") in TEXT_CHANNEL_TYPES]
    chans.sort(key=lambda c: c.get("position", 0))
    return chans


def assignable_roles(guild_id: str) -> list[dict]:
    """Roles attribuables (hors @everyone et roles geres), du plus haut au plus bas."""
    roles = [
        r
        for r in get_guild_roles(guild_id)
        if r["name"] != "@everyone" and not r.get("managed", False)
    ]
    roles.sort(key=lambda r: r.get("position", 0), reverse=True)
    return roles


def can_manage(guild: dict) -> bool:
    """L'utilisateur a-t-il le droit de configurer ce serveur ?"""
    if guild.get("owner"):
        return True
    try:
        perms = int(guild.get("permissions", 0))
    except (TypeError, ValueError):
        perms = 0
    return bool(perms & PERM_ADMINISTRATOR) or bool(perms & PERM_MANAGE_GUILD)


def is_configured() -> bool:
    """Les identifiants OAuth sont-ils renseignes ?"""
    return bool(DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET and DISCORD_TOKEN)
