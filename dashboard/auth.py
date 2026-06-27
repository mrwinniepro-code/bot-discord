"""Authentification 'Se connecter avec Discord' (OAuth2)."""
from __future__ import annotations

import secrets
from functools import wraps

from flask import (
    Blueprint,
    abort,
    redirect,
    request,
    session,
    url_for,
)

from . import discord_api

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login")
def login():
    if not discord_api.is_configured():
        abort(503, "Dashboard non configure (identifiants OAuth manquants dans .env).")
    state = secrets.token_urlsafe(16)
    session["oauth_state"] = state
    return redirect(discord_api.authorize_url(state))


@auth_bp.route("/callback")
def callback():
    if request.args.get("state") != session.pop("oauth_state", None):
        abort(400, "Etat OAuth invalide. Reessaie de te connecter.")
    code = request.args.get("code")
    if not code:
        return redirect(url_for("index"))

    token = discord_api.exchange_code(code)
    access = token["access_token"]
    user = discord_api.get_user(access)
    guilds = discord_api.get_user_guilds(access)

    session["user"] = {
        "id": user["id"],
        "username": user.get("global_name") or user.get("username"),
        "avatar": user.get("avatar"),
    }
    session["access_token"] = access
    session["guilds"] = guilds
    return redirect(url_for("servers"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapper


def get_manageable_guild(guild_id: str) -> dict | None:
    """Renvoie le serveur (dict) si l'utilisateur connecte a le droit de le gerer."""
    for g in session.get("guilds", []):
        if g["id"] == str(guild_id) and discord_api.can_manage(g):
            return g
    return None
