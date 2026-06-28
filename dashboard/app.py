"""Application Flask du dashboard web."""
from __future__ import annotations

import io
import secrets

import requests
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from PIL import Image

from bot.config import (
    BACKGROUNDS_DIR,
    DASHBOARD_PORT,
    FLASK_SECRET_KEY,
)
from bot.database import (
    AutoRole,
    Giveaway,
    LevelReward,
    ModCase,
    ShopItem,
    clear_welcome_background,
    get_guild_config,
    get_welcome_background,
    init_db,
    session_scope,
    set_welcome_background,
)
from bot.utils.images import _render_card, placeholder_avatar_bytes
from bot.utils.modlog import ACTION_LABELS

from . import discord_api
from .auth import auth_bp, get_manageable_guild, login_required

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_UPLOAD = 8 * 1024 * 1024  # 8 Mo


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = FLASK_SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
    init_db()  # cree/maj les tables (utile si le dashboard demarre avant le bot)
    app.register_blueprint(auth_bp)

    # ---- helpers ---- #
    @app.context_processor
    def inject_globals():
        return {
            "current_user": session.get("user"),
            "bot_name": "ChadBot",
            "csrf_token": session.get("csrf", ""),
        }

    @app.before_request
    def ensure_csrf():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(16)

    def check_csrf():
        if request.form.get("csrf") != session.get("csrf"):
            abort(400, "Jeton de securite invalide. Recharge la page.")

    def require_guild(guild_id: str) -> dict:
        guild = get_manageable_guild(guild_id)
        if not guild:
            abort(403)
        return guild

    # ---- pages publiques ---- #
    @app.route("/")
    def index():
        return render_template("index.html", configured=discord_api.is_configured())

    @app.route("/servers")
    @login_required
    def servers():
        try:
            bot_ids = discord_api.get_bot_guild_ids()
        except requests.HTTPError:
            bot_ids = set()
        guilds = [g for g in session.get("guilds", []) if discord_api.can_manage(g)]
        for g in guilds:
            g["bot_in"] = g["id"] in bot_ids
            g["invite"] = discord_api.invite_url(g["id"])
        guilds.sort(key=lambda g: (not g["bot_in"], g["name"].lower()))
        return render_template("servers.html", guilds=guilds)

    # ---- accueil d'un serveur ---- #
    @app.route("/g/<guild_id>")
    @login_required
    def guild_home(guild_id):
        guild = require_guild(guild_id)
        if guild_id not in discord_api.get_bot_guild_ids():
            return render_template(
                "invite.html", guild=guild, invite=discord_api.invite_url(guild_id)
            )
        return render_template("guild_home.html", guild=guild, active="home")

    # ---- module Arrivees / Departs ---- #
    @app.route("/g/<guild_id>/welcome", methods=["GET", "POST"])
    @login_required
    def welcome(guild_id):
        guild = require_guild(guild_id)
        try:
            channels = discord_api.text_channels(guild_id)
        except requests.HTTPError:
            channels = []

        if request.method == "POST":
            check_csrf()
            _save_welcome(guild_id)
            flash("Reglages d'arrivee/depart enregistres.", "success")
            return redirect(url_for("welcome", guild_id=guild_id))

        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            data = {
                "welcome_enabled": cfg.welcome_enabled,
                "welcome_channel_id": cfg.welcome_channel_id,
                "welcome_message": cfg.welcome_message,
                "welcome_card_enabled": cfg.welcome_card_enabled,
                "welcome_card_title": cfg.welcome_card_title,
                "welcome_card_background": cfg.welcome_card_background,
                "leave_enabled": cfg.leave_enabled,
                "leave_channel_id": cfg.leave_channel_id,
                "leave_message": cfg.leave_message,
            }
        return render_template(
            "welcome.html", guild=guild, active="welcome", channels=channels, cfg=data
        )

    def _save_welcome(guild_id: str) -> None:
        form = request.form
        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            cfg.welcome_enabled = form.get("welcome_enabled") == "on"
            cfg.welcome_channel_id = _int_or_none(form.get("welcome_channel_id"))
            cfg.welcome_message = form.get("welcome_message", "").strip() or cfg.welcome_message
            cfg.welcome_card_enabled = form.get("welcome_card_enabled") == "on"
            cfg.welcome_card_title = (form.get("welcome_card_title", "").strip() or "Bienvenue")[:80]

            cfg.leave_enabled = form.get("leave_enabled") == "on"
            cfg.leave_channel_id = _int_or_none(form.get("leave_channel_id"))
            cfg.leave_message = form.get("leave_message", "").strip() or cfg.leave_message

            # --- Fond de la carte ---
            if form.get("remove_background") == "on":
                cfg.welcome_card_background = None
                clear_welcome_background(int(guild_id))
            else:
                saved = _handle_background_upload(guild_id)
                if saved is not None:
                    cfg.welcome_card_background = saved  # marqueur "db"
                else:
                    url = form.get("background_url", "").strip()
                    if url.startswith(("http://", "https://")):
                        cfg.welcome_card_background = url
                        clear_welcome_background(int(guild_id))

    @app.route("/g/<guild_id>/welcome/preview.png")
    @login_required
    def welcome_preview(guild_id):
        require_guild(guild_id)
        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            title, bg = cfg.welcome_card_title, cfg.welcome_card_background
        # Fond : image stockee en base (upload) ou URL telechargee pour l'apercu
        background = None
        if bg == "db":
            background = get_welcome_background(int(guild_id))
        elif bg and bg.startswith(("http://", "https://")):
            try:
                resp = requests.get(bg, timeout=8)
                if resp.status_code == 200:
                    background = resp.content
            except requests.RequestException:
                background = None
        buf = _render_card(placeholder_avatar_bytes(), title, "NouveauMembre", "Membre n°123", background)
        resp = send_file(buf, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---- module Auto-roles ---- #
    @app.route("/g/<guild_id>/autoroles", methods=["GET", "POST"])
    @login_required
    def autoroles(guild_id):
        guild = require_guild(guild_id)
        try:
            roles = discord_api.assignable_roles(guild_id)
        except requests.HTTPError:
            roles = []

        if request.method == "POST":
            check_csrf()
            selected = {int(r) for r in request.form.getlist("roles")}
            with session_scope() as s:
                existing = s.query(AutoRole).filter_by(guild_id=int(guild_id)).all()
                existing_ids = {r.role_id for r in existing}
                for row in existing:
                    if row.role_id not in selected:
                        s.delete(row)
                for rid in selected - existing_ids:
                    s.add(AutoRole(guild_id=int(guild_id), role_id=rid))
            flash("Auto-roles enregistres.", "success")
            return redirect(url_for("autoroles", guild_id=guild_id))

        with session_scope() as s:
            current = {
                r.role_id for r in s.query(AutoRole).filter_by(guild_id=int(guild_id)).all()
            }
        return render_template(
            "autoroles.html", guild=guild, active="autoroles", roles=roles, current=current
        )

    # ---- module Logs ---- #
    @app.route("/g/<guild_id>/logs", methods=["GET", "POST"])
    @login_required
    def logs(guild_id):
        guild = require_guild(guild_id)
        try:
            channels = discord_api.text_channels(guild_id)
        except requests.HTTPError:
            channels = []

        if request.method == "POST":
            check_csrf()
            form = request.form
            with session_scope() as s:
                cfg = get_guild_config(s, int(guild_id))
                cfg.logs_enabled = form.get("logs_enabled") == "on"
                cfg.logs_channel_id = _int_or_none(form.get("logs_channel_id"))
                cfg.log_joins = form.get("log_joins") == "on"
                cfg.log_leaves = form.get("log_leaves") == "on"
                cfg.log_message_delete = form.get("log_message_delete") == "on"
                cfg.log_message_edit = form.get("log_message_edit") == "on"
                cfg.log_moderation = form.get("log_moderation") == "on"
            flash("Réglages des logs enregistrés.", "success")
            return redirect(url_for("logs", guild_id=guild_id))

        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            data = {
                k: getattr(cfg, k)
                for k in (
                    "logs_enabled", "logs_channel_id", "log_joins", "log_leaves",
                    "log_message_delete", "log_message_edit", "log_moderation",
                )
            }
        return render_template("logs.html", guild=guild, active="logs", channels=channels, cfg=data)

    # ---- module Auto-modération ---- #
    @app.route("/g/<guild_id>/automod", methods=["GET", "POST"])
    @login_required
    def automod(guild_id):
        guild = require_guild(guild_id)
        if request.method == "POST":
            check_csrf()
            form = request.form
            with session_scope() as s:
                cfg = get_guild_config(s, int(guild_id))
                cfg.automod_antispam_enabled = form.get("antispam") == "on"
                cfg.automod_antispam_count = _int_or(form.get("antispam_count"), 5, 2, 30)
                cfg.automod_antispam_seconds = _int_or(form.get("antispam_seconds"), 5, 1, 60)
                cfg.automod_antilink_enabled = form.get("antilink") == "on"
                cfg.automod_antilink_whitelist = form.get("whitelist", "").strip()
                cfg.automod_badwords_enabled = form.get("badwords_on") == "on"
                cfg.automod_badwords = form.get("badwords", "").strip()
            flash("Réglages d'auto-modération enregistrés.", "success")
            return redirect(url_for("automod", guild_id=guild_id))

        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            data = {
                "antispam": cfg.automod_antispam_enabled,
                "antispam_count": cfg.automod_antispam_count,
                "antispam_seconds": cfg.automod_antispam_seconds,
                "antilink": cfg.automod_antilink_enabled,
                "whitelist": cfg.automod_antilink_whitelist,
                "badwords_on": cfg.automod_badwords_enabled,
                "badwords": cfg.automod_badwords,
            }
        return render_template("automod.html", guild=guild, active="automod", cfg=data)

    # ---- module Modération (casier) ---- #
    @app.route("/g/<guild_id>/moderation", methods=["GET", "POST"])
    @login_required
    def moderation(guild_id):
        guild = require_guild(guild_id)
        if request.method == "POST":
            check_csrf()
            case_id = _int_or_none(request.form.get("delete_case"))
            if case_id:
                with session_scope() as s:
                    c = s.get(ModCase, case_id)
                    if c and c.guild_id == int(guild_id):
                        s.delete(c)
                flash("Dossier supprimé.", "success")
            return redirect(url_for("moderation", guild_id=guild_id))

        with session_scope() as s:
            cases = (
                s.query(ModCase)
                .filter_by(guild_id=int(guild_id))
                .order_by(ModCase.created_at.desc())
                .limit(100)
                .all()
            )
            rows = [
                {
                    "id": c.id, "user_id": c.user_id, "moderator_id": c.moderator_id,
                    "action": c.action, "reason": c.reason, "created": c.created_at,
                }
                for c in cases
            ]
        return render_template(
            "moderation.html", guild=guild, active="moderation", cases=rows, labels=ACTION_LABELS
        )

    # ---- module Tickets ---- #
    @app.route("/g/<guild_id>/tickets", methods=["GET", "POST"])
    @login_required
    def tickets(guild_id):
        guild = require_guild(guild_id)
        try:
            cats = discord_api.categories(guild_id)
            channels = discord_api.text_channels(guild_id)
            roles = discord_api.assignable_roles(guild_id)
        except requests.HTTPError:
            cats, channels, roles = [], [], []

        if request.method == "POST":
            check_csrf()
            form = request.form
            with session_scope() as s:
                cfg = get_guild_config(s, int(guild_id))
                cfg.tickets_enabled = form.get("tickets_enabled") == "on"
                cfg.ticket_category_id = _int_or_none(form.get("ticket_category_id"))
                cfg.ticket_support_role_id = _int_or_none(form.get("ticket_support_role_id"))
                cfg.ticket_open_message = (
                    form.get("ticket_open_message", "").strip() or cfg.ticket_open_message
                )
            flash("Réglages des tickets enregistrés.", "success")
            return redirect(url_for("tickets", guild_id=guild_id))

        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            data = {
                "tickets_enabled": cfg.tickets_enabled,
                "ticket_category_id": cfg.ticket_category_id,
                "ticket_support_role_id": cfg.ticket_support_role_id,
                "ticket_open_message": cfg.ticket_open_message,
            }
        return render_template(
            "tickets.html", guild=guild, active="tickets",
            categories=cats, channels=channels, roles=roles, cfg=data,
        )

    # ---- module Suggestions ---- #
    @app.route("/g/<guild_id>/suggestions", methods=["GET", "POST"])
    @login_required
    def suggestions(guild_id):
        guild = require_guild(guild_id)
        try:
            channels = discord_api.text_channels(guild_id)
        except requests.HTTPError:
            channels = []

        if request.method == "POST":
            check_csrf()
            form = request.form
            with session_scope() as s:
                cfg = get_guild_config(s, int(guild_id))
                cfg.suggestions_enabled = form.get("suggestions_enabled") == "on"
                cfg.suggestions_channel_id = _int_or_none(form.get("suggestions_channel_id"))
            flash("Réglages des suggestions enregistrés.", "success")
            return redirect(url_for("suggestions", guild_id=guild_id))

        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            data = {
                "suggestions_enabled": cfg.suggestions_enabled,
                "suggestions_channel_id": cfg.suggestions_channel_id,
            }
        return render_template(
            "suggestions.html", guild=guild, active="suggestions", channels=channels, cfg=data
        )

    # ---- module Giveaways (liste) ---- #
    @app.route("/g/<guild_id>/giveaways")
    @login_required
    def giveaways(guild_id):
        guild = require_guild(guild_id)
        with session_scope() as s:
            rows = (
                s.query(Giveaway)
                .filter_by(guild_id=int(guild_id))
                .order_by(Giveaway.ended, Giveaway.end_time.desc())
                .limit(50)
                .all()
            )
            items = [
                {
                    "id": g.id, "prize": g.prize, "winners": g.winners_count,
                    "end_time": g.end_time, "ended": g.ended, "entries": len(g.entries),
                }
                for g in rows
            ]
        return render_template("giveaways.html", guild=guild, active="giveaways", giveaways=items)

    # ---- module Niveaux ---- #
    @app.route("/g/<guild_id>/levels", methods=["GET", "POST"])
    @login_required
    def levels(guild_id):
        guild = require_guild(guild_id)
        try:
            channels = discord_api.text_channels(guild_id)
            roles = discord_api.assignable_roles(guild_id)
        except requests.HTTPError:
            channels, roles = [], []

        if request.method == "POST":
            check_csrf()
            action = request.form.get("action")
            with session_scope() as s:
                if action == "add_reward":
                    lvl = _int_or(request.form.get("level"), 1, 1, 1000)
                    rid = _int_or_none(request.form.get("role_id"))
                    if rid:
                        s.add(LevelReward(guild_id=int(guild_id), level=lvl, role_id=rid))
                    flash("Récompense ajoutée.", "success")
                elif action == "del_reward":
                    rw = s.get(LevelReward, _int_or_none(request.form.get("reward_id")))
                    if rw and rw.guild_id == int(guild_id):
                        s.delete(rw)
                    flash("Récompense supprimée.", "success")
                else:  # save
                    cfg = get_guild_config(s, int(guild_id))
                    cfg.levels_enabled = request.form.get("levels_enabled") == "on"
                    cfg.levelup_announce = request.form.get("levelup_announce") == "on"
                    cfg.levelup_channel_id = _int_or_none(request.form.get("levelup_channel_id"))
                    cfg.levelup_message = (
                        request.form.get("levelup_message", "").strip() or cfg.levelup_message
                    )
                    flash("Réglages des niveaux enregistrés.", "success")
            return redirect(url_for("levels", guild_id=guild_id))

        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            data = {
                "levels_enabled": cfg.levels_enabled,
                "levelup_announce": cfg.levelup_announce,
                "levelup_channel_id": cfg.levelup_channel_id,
                "levelup_message": cfg.levelup_message,
            }
            rewards = (
                s.query(LevelReward)
                .filter_by(guild_id=int(guild_id))
                .order_by(LevelReward.level)
                .all()
            )
            reward_rows = [{"id": r.id, "level": r.level, "role_id": r.role_id} for r in rewards]
        return render_template(
            "levels.html", guild=guild, active="levels",
            channels=channels, roles=roles, cfg=data, rewards=reward_rows,
        )

    # ---- module Economie ---- #
    @app.route("/g/<guild_id>/economy", methods=["GET", "POST"])
    @login_required
    def economy(guild_id):
        guild = require_guild(guild_id)
        try:
            roles = discord_api.assignable_roles(guild_id)
        except requests.HTTPError:
            roles = []

        if request.method == "POST":
            check_csrf()
            action = request.form.get("action")
            with session_scope() as s:
                if action == "add_item":
                    rid = _int_or_none(request.form.get("role_id"))
                    price = _int_or(request.form.get("price"), 100, 1, 100000000)
                    iname = request.form.get("name", "").strip()[:100]
                    if rid and iname:
                        s.add(ShopItem(guild_id=int(guild_id), role_id=rid, name=iname, price=price))
                    flash("Article ajouté à la boutique.", "success")
                elif action == "del_item":
                    it = s.get(ShopItem, _int_or_none(request.form.get("item_id")))
                    if it and it.guild_id == int(guild_id):
                        s.delete(it)
                    flash("Article supprimé.", "success")
                else:  # save
                    cfg = get_guild_config(s, int(guild_id))
                    cfg.economy_enabled = request.form.get("economy_enabled") == "on"
                    cfg.currency_name = (request.form.get("currency_name", "").strip() or "pièces")[:40]
                    cfg.currency_symbol = (request.form.get("currency_symbol", "").strip() or "🪙")[:16]
                    cfg.daily_amount = _int_or(request.form.get("daily_amount"), 100, 0, 100000000)
                    cfg.work_min = _int_or(request.form.get("work_min"), 20, 0, 100000000)
                    cfg.work_max = _int_or(request.form.get("work_max"), 80, 0, 100000000)
                    flash("Réglages d'économie enregistrés.", "success")
            return redirect(url_for("economy", guild_id=guild_id))

        with session_scope() as s:
            cfg = get_guild_config(s, int(guild_id))
            data = {
                "economy_enabled": cfg.economy_enabled,
                "currency_name": cfg.currency_name,
                "currency_symbol": cfg.currency_symbol,
                "daily_amount": cfg.daily_amount,
                "work_min": cfg.work_min,
                "work_max": cfg.work_max,
            }
            items = s.query(ShopItem).filter_by(guild_id=int(guild_id)).order_by(ShopItem.price).all()
            item_rows = [{"id": it.id, "name": it.name, "role_id": it.role_id, "price": it.price} for it in items]
        return render_template(
            "economy.html", guild=guild, active="economy", roles=roles, cfg=data, items=item_rows
        )

    def _handle_background_upload(guild_id: str):
        """Stocke un fond uploade DANS LA BASE (accessible par le bot du telephone).

        Renvoie le marqueur "db", ou None si pas de fichier valide.
        """
        file = request.files.get("background_file")
        if not file or not file.filename:
            return None
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in ALLOWED_IMAGE_EXT:
            flash("Format d'image non supporte (png, jpg, webp, gif).", "danger")
            return None
        raw = file.read()
        try:
            Image.open(io.BytesIO(raw)).verify()
        except Exception:
            flash("Le fichier n'est pas une image valide.", "danger")
            return None
        set_welcome_background(int(guild_id), raw)
        return "db"

    return app


def _int_or_none(value):
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _int_or(value, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=DASHBOARD_PORT, debug=True)
