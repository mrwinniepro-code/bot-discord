"""Modeles de base de donnees (SQLAlchemy) partages entre le bot et le dashboard.

On utilise SQLite par defaut (zero configuration). Tout passe par SQLAlchemy donc
on pourra basculer sur PostgreSQL plus tard en changeant juste DATABASE_URL.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


class GuildConfig(Base):
    """Reglages d'un serveur (une ligne par serveur)."""

    __tablename__ = "guild_config"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # --- Arrivees ---
    welcome_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    welcome_message: Mapped[str] = mapped_column(
        Text, default="Bienvenue {user_mention} sur **{server}** ! 🎉 Tu es notre {count}e membre."
    )
    welcome_card_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    welcome_card_title: Mapped[str] = mapped_column(String(80), default="Bienvenue")
    welcome_card_background: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # --- Departs ---
    leave_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    leave_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    leave_message: Mapped[str] = mapped_column(
        Text, default="**{user_name}** a quitte le serveur. 👋"
    )

    # --- Logs ---
    logs_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    logs_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    log_joins: Mapped[bool] = mapped_column(Boolean, default=True)
    log_leaves: Mapped[bool] = mapped_column(Boolean, default=True)
    log_message_delete: Mapped[bool] = mapped_column(Boolean, default=True)
    log_message_edit: Mapped[bool] = mapped_column(Boolean, default=True)
    log_moderation: Mapped[bool] = mapped_column(Boolean, default=True)

    # --- Auto-moderation ---
    automod_antispam_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    automod_antispam_count: Mapped[int] = mapped_column(Integer, default=5)
    automod_antispam_seconds: Mapped[int] = mapped_column(Integer, default=5)
    automod_antilink_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    automod_antilink_whitelist: Mapped[str] = mapped_column(Text, default="")
    automod_badwords_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    automod_badwords: Mapped[str] = mapped_column(Text, default="")

    # --- Tickets ---
    tickets_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    ticket_category_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ticket_support_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ticket_open_message: Mapped[str] = mapped_column(
        Text, default="Merci d'avoir ouvert un ticket ! Un membre du staff va te repondre. 🎫"
    )

    # --- Suggestions ---
    suggestions_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    suggestions_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # --- Niveaux (XP) ---
    levels_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    levelup_announce: Mapped[bool] = mapped_column(Boolean, default=True)
    levelup_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    levelup_message: Mapped[str] = mapped_column(
        Text, default="🎉 Bravo {user_mention}, tu passes niveau **{level}** !"
    )

    # --- Economie ---
    economy_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    currency_name: Mapped[str] = mapped_column(String(40), default="pièces")
    currency_symbol: Mapped[str] = mapped_column(String(16), default="🪙")
    daily_amount: Mapped[int] = mapped_column(Integer, default=100)
    work_min: Mapped[int] = mapped_column(Integer, default=20)
    work_max: Mapped[int] = mapped_column(Integer, default=80)


class AutoRole(Base):
    """Roles attribues automatiquement a chaque arrivee."""

    __tablename__ = "auto_role"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role_id: Mapped[int] = mapped_column(BigInteger)


class ReactionRolePanel(Base):
    """Un panneau de roles a reaction (un message avec des boutons)."""

    __tablename__ = "reaction_role_panel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="Choisis tes roles")
    description: Mapped[str] = mapped_column(Text, default="")

    entries: Mapped[list["ReactionRoleEntry"]] = relationship(
        back_populates="panel",
        cascade="all, delete-orphan",
        order_by="ReactionRoleEntry.id",
    )


class ReactionRoleEntry(Base):
    """Un bouton de role dans un panneau."""

    __tablename__ = "reaction_role_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    panel_id: Mapped[int] = mapped_column(
        ForeignKey("reaction_role_panel.id", ondelete="CASCADE"), index=True
    )
    role_id: Mapped[int] = mapped_column(BigInteger)
    label: Mapped[str] = mapped_column(String(80))
    emoji: Mapped[str | None] = mapped_column(String(100), nullable=True)

    panel: Mapped["ReactionRolePanel"] = relationship(back_populates="entries")


class ModCase(Base):
    """Une entree du casier : sanction ou avertissement."""

    __tablename__ = "mod_case"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    moderator_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(20))  # warn / mute / kick / ban / unmute / unban
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class Ticket(Base):
    """Un ticket = un salon prive ouvert par un membre."""

    __tablename__ = "ticket"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    open: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )


class Giveaway(Base):
    """Un giveaway (tirage au sort)."""

    __tablename__ = "giveaway"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    host_id: Mapped[int] = mapped_column(BigInteger)
    prize: Mapped[str] = mapped_column(String(255))
    winners_count: Mapped[int] = mapped_column(Integer, default=1)
    end_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    ended: Mapped[bool] = mapped_column(Boolean, default=False)

    entries: Mapped[list["GiveawayEntry"]] = relationship(
        back_populates="giveaway", cascade="all, delete-orphan"
    )


class GiveawayEntry(Base):
    """Une participation a un giveaway."""

    __tablename__ = "giveaway_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    giveaway_id: Mapped[int] = mapped_column(
        ForeignKey("giveaway.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(BigInteger)

    giveaway: Mapped["Giveaway"] = relationship(back_populates="entries")


class UserLevel(Base):
    """XP et niveau d'un membre sur un serveur."""

    __tablename__ = "user_level"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LevelReward(Base):
    """Role attribue automatiquement a l'atteinte d'un niveau."""

    __tablename__ = "level_reward"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    level: Mapped[int] = mapped_column(Integer)
    role_id: Mapped[int] = mapped_column(BigInteger)


class UserEconomy(Base):
    """Porte-monnaie d'un membre sur un serveur."""

    __tablename__ = "user_economy"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    balance: Mapped[int] = mapped_column(Integer, default=0)
    last_daily: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_work: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ShopItem(Base):
    """Un article de la boutique (un role a acheter)."""

    __tablename__ = "shop_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)


# --- Moteur & sessions ---
# check_same_thread=False : utile car le bot (asyncio) et le dashboard (Flask)
# peuvent toucher la base depuis des threads differents.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        """WAL = lectures/ecritures concurrentes (bot + dashboard) sans blocage."""
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


def _auto_migrate() -> None:
    """Ajoute les colonnes manquantes aux tables existantes (migration legere SQLite).

    create_all() cree les tables absentes mais PAS les colonnes ajoutees apres coup.
    On compare donc le modele a la table reelle et on ALTER TABLE au besoin.
    """
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            coltype = col.type.compile(engine.dialect)
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
            default = getattr(col.default, "arg", None)
            if default is not None and not callable(default):
                if isinstance(default, bool):
                    default = 1 if default else 0
                if isinstance(default, str):
                    default = "'" + default.replace("'", "''") + "'"
                ddl += f" DEFAULT {default}"
            with engine.begin() as conn:
                conn.execute(text(ddl))


def init_db() -> None:
    """Cree les tables manquantes puis ajoute les colonnes manquantes."""
    Base.metadata.create_all(engine)
    _auto_migrate()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Ouvre une session, commit a la fin, rollback en cas d'erreur."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_guild_config(session: Session, guild_id: int) -> GuildConfig:
    """Recupere la config d'un serveur, en la creant si elle n'existe pas."""
    cfg = session.get(GuildConfig, guild_id)
    if cfg is None:
        cfg = GuildConfig(guild_id=guild_id)
        session.add(cfg)
        session.flush()
    return cfg
