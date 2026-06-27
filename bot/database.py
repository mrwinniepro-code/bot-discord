"""Modeles de base de donnees (SQLAlchemy) partages entre le bot et le dashboard.

On utilise SQLite par defaut (zero configuration). Tout passe par SQLAlchemy donc
on pourra basculer sur PostgreSQL plus tard en changeant juste DATABASE_URL.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
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


# --- Moteur & sessions ---
# check_same_thread=False : utile car le bot (asyncio) et le dashboard (Flask)
# peuvent toucher la base depuis des threads differents.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    """Cree les tables si elles n'existent pas encore."""
    Base.metadata.create_all(engine)


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
