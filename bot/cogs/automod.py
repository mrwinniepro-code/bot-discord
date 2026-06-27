"""Module Auto-moderation : anti-spam, anti-lien, filtre de mots."""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands

from ..database import get_guild_config, session_scope
from ..utils.modlog import send_log

log = logging.getLogger("bot.automod")

LINK_RE = re.compile(
    r"(https?://\S+|discord\.gg/\S+|\b[\w-]+\.(?:com|net|org|fr|gg|io|me|tv|xyz|co|app)\b)",
    re.IGNORECASE,
)

# Domaines toujours autorises (GIF du selecteur Discord, medias Discord).
# Evite de supprimer les GIF Tenor/Giphy inseres par le bouton GIF de Discord.
DEFAULT_LINK_WHITELIST = {
    "tenor.com",
    "giphy.com",
    "media.discordapp.net",
    "cdn.discordapp.com",
    "images-ext-1.discordapp.net",
    "images-ext-2.discordapp.net",
    "discordapp.com",
    "discord.com",
}

CACHE_TTL = 15  # secondes


class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cache: dict[int, tuple[dict, float]] = {}
        self._spam: dict[tuple[int, int], deque] = defaultdict(deque)

    # ------------------------------------------------------------------ #
    #  Config (avec petit cache pour ne pas lire la DB a chaque message)  #
    # ------------------------------------------------------------------ #
    def _get_cfg(self, guild_id: int) -> dict:
        now = time.time()
        cached = self._cache.get(guild_id)
        if cached and cached[1] > now:
            return cached[0]
        with session_scope() as s:
            cfg = get_guild_config(s, guild_id)
            snap = {
                "antispam": cfg.automod_antispam_enabled,
                "antispam_count": max(2, cfg.automod_antispam_count),
                "antispam_seconds": max(1, cfg.automod_antispam_seconds),
                "antilink": cfg.automod_antilink_enabled,
                "whitelist": cfg.automod_antilink_whitelist or "",
                "badwords_on": cfg.automod_badwords_enabled,
                "badwords": cfg.automod_badwords or "",
            }
        self._cache[guild_id] = (snap, now + CACHE_TTL)
        return snap

    # ------------------------------------------------------------------ #
    #  Detection                                                          #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _has_forbidden_link(content: str, whitelist: str) -> bool:
        if not LINK_RE.search(content):
            return False
        allowed = set(DEFAULT_LINK_WHITELIST)
        allowed.update(w.strip().lower() for w in whitelist.split(",") if w.strip())
        # Chaque lien detecte doit etre autorise ; sinon le message est bloque.
        for match in LINK_RE.finditer(content):
            link = match.group(0).lower()
            if not any(domain in link for domain in allowed):
                return True
        return False

    @staticmethod
    def _find_badword(content: str, words: str) -> str | None:
        low = content.lower()
        for w in (x.strip().lower() for x in words.split(",") if x.strip()):
            if re.search(r"\b" + re.escape(w) + r"\b", low):
                return w
        return None

    def _is_spam(self, message: discord.Message, cfg: dict) -> bool:
        key = (message.guild.id, message.author.id)
        now = message.created_at.timestamp()
        dq = self._spam[key]
        dq.append(now)
        while dq and now - dq[0] > cfg["antispam_seconds"]:
            dq.popleft()
        if len(dq) >= cfg["antispam_count"]:
            dq.clear()
            return True
        return False

    # ------------------------------------------------------------------ #
    #  Evenement                                                          #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        member = message.author
        if isinstance(member, discord.Member):
            perms = member.guild_permissions
            if perms.administrator or perms.manage_guild or perms.manage_messages:
                return  # modos exemptes

        cfg = self._get_cfg(message.guild.id)
        if not (cfg["antispam"] or cfg["antilink"] or cfg["badwords_on"]):
            return

        if cfg["antilink"] and message.content and self._has_forbidden_link(
            message.content, cfg["whitelist"]
        ):
            return await self._punish(message, "lien non autorise", spam=False)

        if cfg["badwords_on"] and message.content and self._find_badword(
            message.content, cfg["badwords"]
        ):
            return await self._punish(message, "mot interdit", spam=False)

        if cfg["antispam"] and self._is_spam(message, cfg):
            return await self._punish(message, "spam", spam=True)

    # ------------------------------------------------------------------ #
    #  Sanction                                                           #
    # ------------------------------------------------------------------ #
    async def _punish(self, message: discord.Message, reason: str, spam: bool) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        extra = None
        if spam and isinstance(message.author, discord.Member):
            try:
                await message.author.timeout(timedelta(minutes=5), reason="Auto-mod : spam")
                extra = "Mute automatique de 5 minutes"
            except discord.Forbidden:
                pass

        try:
            await message.channel.send(
                f"🚫 {message.author.mention}, ton message a ete supprime ({reason}).",
                delete_after=5,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            pass

        embed = discord.Embed(
            title="🤖 Auto-modération",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Membre", value=f"{message.author.mention} (`{message.author}`)", inline=True)
        embed.add_field(name="Motif", value=reason, inline=True)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        embed.add_field(name="Message", value=(message.content or "(vide)")[:1000], inline=False)
        if extra:
            embed.add_field(name="Action", value=extra, inline=False)
        await send_log(self.bot, message.guild, embed, category="moderation")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
