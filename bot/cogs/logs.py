"""Module Logs : journalise arrivees, departs, messages supprimes/edites."""
from __future__ import annotations

import discord
from discord.ext import commands
from discord.utils import format_dt

from ..utils.modlog import send_log


class Logs(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = discord.Embed(
            title="📥 Arrivée d'un membre",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Membre", value=f"{member.mention}\n`{member}` (`{member.id}`)", inline=True)
        embed.add_field(name="Compte créé", value=format_dt(member.created_at, "R"), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await send_log(self.bot, member.guild, embed, category="join")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        roles = [r.mention for r in member.roles if not r.is_default()]
        embed = discord.Embed(
            title="📤 Départ d'un membre",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Membre", value=f"`{member}` (`{member.id}`)", inline=True)
        if roles:
            embed.add_field(name="Rôles", value=" ".join(roles)[:1024], inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await send_log(self.bot, member.guild, embed, category="leave")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        embed = discord.Embed(
            title="🗑️ Message supprimé",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Auteur", value=f"{message.author.mention} (`{message.author}`)", inline=True)
        embed.add_field(name="Salon", value=message.channel.mention, inline=True)
        if message.content:
            embed.add_field(name="Contenu", value=message.content[:1024], inline=False)
        if message.attachments:
            embed.add_field(
                name="Pièces jointes",
                value=", ".join(a.filename for a in message.attachments)[:1024],
                inline=False,
            )
        await send_log(self.bot, message.guild, embed, category="message_delete")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.guild is None or after.author.bot:
            return
        if before.content == after.content:
            return
        embed = discord.Embed(
            title="✏️ Message modifié",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
            description=f"[Aller au message]({after.jump_url})",
        )
        embed.add_field(name="Auteur", value=f"{after.author.mention} (`{after.author}`)", inline=True)
        embed.add_field(name="Salon", value=after.channel.mention, inline=True)
        embed.add_field(name="Avant", value=(before.content or "(vide)")[:1024], inline=False)
        embed.add_field(name="Après", value=(after.content or "(vide)")[:1024], inline=False)
        await send_log(self.bot, after.guild, embed, category="message_edit")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logs(bot))
