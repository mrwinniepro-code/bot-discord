"""Module Niveaux : XP par message, carte de niveau, classement, recompenses."""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ..database import LevelReward, UserLevel, get_guild_config, session_scope
from ..utils.checks import bot_can_manage_role
from ..utils.images import generate_rank_card
from ..utils.leveling import level_details

log = logging.getLogger("bot.levels")

XP_COOLDOWN = 60          # secondes entre deux gains d'XP
XP_MIN, XP_MAX = 15, 25   # XP gagnee par message


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Levels(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._enabled_cache: dict[int, tuple[bool, float]] = {}
        self._cooldowns: dict[tuple[int, int], float] = {}

    def _levels_enabled(self, guild_id: int) -> bool:
        now = time.time()
        cached = self._enabled_cache.get(guild_id)
        if cached and cached[1] > now:
            return cached[0]
        with session_scope() as s:
            enabled = get_guild_config(s, guild_id).levels_enabled
        self._enabled_cache[guild_id] = (enabled, now + 30)
        return enabled

    # ------------------------------------------------------------------ #
    #  Gain d'XP                                                          #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        gid, uid = message.guild.id, message.author.id
        if not self._levels_enabled(gid):
            return
        now = time.time()
        key = (gid, uid)
        if now - self._cooldowns.get(key, 0.0) < XP_COOLDOWN:
            return
        self._cooldowns[key] = now

        gained = random.randint(XP_MIN, XP_MAX)
        with session_scope() as s:
            ul = s.get(UserLevel, (gid, uid))
            if ul is None:
                ul = UserLevel(guild_id=gid, user_id=uid, xp=0, level=0)
                s.add(ul)
            old_level = ul.level
            ul.xp += gained
            ul.last_message_at = _utcnow()
            new_level, _, _ = level_details(ul.xp)
            ul.level = new_level

        if new_level > old_level:
            await self._on_level_up(message, new_level)

    async def _on_level_up(self, message: discord.Message, level: int) -> None:
        member = message.author
        with session_scope() as s:
            rewards = (
                s.query(LevelReward)
                .filter(LevelReward.guild_id == message.guild.id, LevelReward.level <= level)
                .all()
            )
            reward_role_ids = [r.role_id for r in rewards]
            cfg = get_guild_config(s, message.guild.id)
            announce, channel_id, template = (
                cfg.levelup_announce, cfg.levelup_channel_id, cfg.levelup_message,
            )

        for rid in reward_role_ids:
            role = message.guild.get_role(rid)
            if role and role not in member.roles and bot_can_manage_role(message.guild, role):
                try:
                    await member.add_roles(role, reason=f"Récompense niveau {level}")
                except discord.Forbidden:
                    pass

        if announce:
            text = (
                template.replace("{user_mention}", member.mention)
                .replace("{user}", member.display_name)
                .replace("{level}", str(level))
                .replace("{server}", message.guild.name)
            )
            channel = message.guild.get_channel(channel_id) if channel_id else message.channel
            if channel:
                try:
                    await channel.send(text, allowed_mentions=discord.AllowedMentions(users=True))
                except discord.Forbidden:
                    pass

    # ------------------------------------------------------------------ #
    #  Commandes                                                          #
    # ------------------------------------------------------------------ #
    @app_commands.command(name="niveau", description="Affiche ta carte de niveau (ou celle d'un membre).")
    @app_commands.describe(membre="Membre dont voir le niveau (optionnel)")
    @app_commands.guild_only()
    async def niveau(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        member = membre or interaction.user
        with session_scope() as s:
            ul = s.get(UserLevel, (interaction.guild_id, member.id))
            xp = ul.xp if ul else 0
            rank = (
                s.query(UserLevel)
                .filter(UserLevel.guild_id == interaction.guild_id, UserLevel.xp > xp)
                .count()
                + 1
            )
        level, into, needed = level_details(xp)
        await interaction.response.defer()
        buf = await generate_rank_card(member, level, rank, into, needed)
        await interaction.followup.send(file=discord.File(buf, filename="niveau.png"))

    @app_commands.command(name="classement", description="Affiche le top 10 des niveaux du serveur.")
    @app_commands.guild_only()
    async def classement(self, interaction: discord.Interaction) -> None:
        with session_scope() as s:
            top = (
                s.query(UserLevel)
                .filter_by(guild_id=interaction.guild_id)
                .order_by(UserLevel.xp.desc())
                .limit(10)
                .all()
            )
            rows = [(u.user_id, u.xp, u.level) for u in top]
        if not rows:
            return await interaction.response.send_message(
                "Personne n'a encore d'XP. Discutez pour en gagner !", ephemeral=True
            )
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, (uid, xp, lvl) in enumerate(rows, start=1):
            member = interaction.guild.get_member(uid)
            name = member.display_name if member else f"Utilisateur {uid}"
            lines.append(f"{medals.get(i, f'**{i}.**')} {name} — niveau **{lvl}** ({xp} XP)")
        embed = discord.Embed(
            title="🏆 Classement",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Levels(bot))
