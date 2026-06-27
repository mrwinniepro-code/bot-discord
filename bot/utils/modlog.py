"""Envoi des messages de logs dans le salon configure."""
from __future__ import annotations

import logging

import discord

from ..database import get_guild_config, session_scope

log = logging.getLogger("bot.modlog")

# Categorie de log -> nom de la colonne d'activation dans GuildConfig
_CATEGORY_TOGGLE = {
    "join": "log_joins",
    "leave": "log_leaves",
    "message_delete": "log_message_delete",
    "message_edit": "log_message_edit",
    "moderation": "log_moderation",
}


async def send_log(
    bot: discord.Client,
    guild: discord.Guild,
    embed: discord.Embed,
    category: str | None = None,
) -> None:
    """Envoie un embed dans le salon de logs si les logs (et la categorie) sont actives."""
    with session_scope() as s:
        cfg = get_guild_config(s, guild.id)
        if not cfg.logs_enabled or not cfg.logs_channel_id:
            return
        if category and not getattr(cfg, _CATEGORY_TOGGLE.get(category, ""), True):
            return
        channel_id = cfg.logs_channel_id

    channel = guild.get_channel(channel_id)
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return
    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.Forbidden:
        log.warning("Permission manquante pour ecrire dans le salon de logs (%s)", channel_id)


# Couleurs par type d'action
ACTION_COLORS = {
    "warn": discord.Color.yellow(),
    "mute": discord.Color.orange(),
    "unmute": discord.Color.green(),
    "kick": discord.Color.orange(),
    "ban": discord.Color.red(),
    "unban": discord.Color.green(),
}

ACTION_LABELS = {
    "warn": "⚠️ Avertissement",
    "mute": "🔇 Mute",
    "unmute": "🔊 Unmute",
    "kick": "👢 Expulsion",
    "ban": "🔨 Bannissement",
    "unban": "♻️ Debannissement",
}


def moderation_embed(
    action: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str,
    case_id: int | None = None,
    extra: str | None = None,
) -> discord.Embed:
    """Construit l'embed de log pour une action de moderation."""
    embed = discord.Embed(
        title=ACTION_LABELS.get(action, action.title()),
        color=ACTION_COLORS.get(action, discord.Color.blurple()),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Membre", value=f"{target.mention}\n`{target}` (`{target.id}`)", inline=True)
    embed.add_field(name="Moderateur", value=f"{moderator.mention}", inline=True)
    embed.add_field(name="Raison", value=reason or "Aucune raison fournie", inline=False)
    if extra:
        embed.add_field(name="Details", value=extra, inline=False)
    if case_id is not None:
        embed.set_footer(text=f"Dossier #{case_id}")
    return embed
