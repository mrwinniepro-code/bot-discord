"""Module Sondages & Suggestions."""
from __future__ import annotations

import logging
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands

from ..database import get_guild_config, session_scope

log = logging.getLogger("bot.polls")


class Polls(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="sondage", description="Crée un sondage (vote natif Discord).")
    @app_commands.describe(
        question="La question du sondage",
        choix1="Premier choix",
        choix2="Deuxième choix",
        choix3="Troisième choix (optionnel)",
        choix4="Quatrième choix (optionnel)",
        choix5="Cinquième choix (optionnel)",
        duree_heures="Durée du sondage en heures (1 à 168, défaut 24)",
    )
    @app_commands.guild_only()
    async def sondage(
        self,
        interaction: discord.Interaction,
        question: str,
        choix1: str,
        choix2: str,
        choix3: str | None = None,
        choix4: str | None = None,
        choix5: str | None = None,
        duree_heures: app_commands.Range[int, 1, 168] = 24,
    ) -> None:
        poll = discord.Poll(question=question[:300], duration=timedelta(hours=duree_heures))
        for choix in (choix1, choix2, choix3, choix4, choix5):
            if choix:
                poll.add_answer(text=choix[:55])
        try:
            await interaction.channel.send(poll=poll)
        except discord.HTTPException as exc:
            return await interaction.response.send_message(
                f"❌ Impossible de créer le sondage : {exc}", ephemeral=True
            )
        await interaction.response.send_message("✅ Sondage publié !", ephemeral=True)

    @app_commands.command(name="suggestion", description="Propose une suggestion dans le salon dédié.")
    @app_commands.describe(suggestion="Ta suggestion")
    @app_commands.guild_only()
    async def suggestion(self, interaction: discord.Interaction, suggestion: str) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            enabled = cfg.suggestions_enabled
            channel_id = cfg.suggestions_channel_id
        if not enabled or not channel_id:
            return await interaction.response.send_message(
                "💡 Les suggestions ne sont pas activées (à configurer dans le dashboard).",
                ephemeral=True,
            )
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message(
                "❌ Salon de suggestions introuvable.", ephemeral=True
            )

        embed = discord.Embed(
            title="💡 Nouvelle suggestion",
            description=suggestion[:2000],
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        try:
            msg = await channel.send(embed=embed)
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
        except discord.Forbidden:
            return await interaction.response.send_message(
                f"❌ Je ne peux pas écrire dans {channel.mention}.", ephemeral=True
            )
        await interaction.response.send_message(
            f"✅ Ta suggestion a été publiée dans {channel.mention} !", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Polls(bot))
