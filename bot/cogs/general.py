"""Commandes generales : /ping et /aide."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class General(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Verifie que le bot repond et affiche sa latence.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"🏓 Pong ! Latence : **{latency} ms**", ephemeral=True
        )

    @app_commands.command(name="aide", description="Affiche les fonctionnalites disponibles.")
    async def aide(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="🤖 Aide du bot",
            description="Voici les modules disponibles. Les commandes de configuration "
            "sont reservees aux membres ayant la permission **Gerer le serveur**.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="👋 Arrivees / Departs",
            value="`/bienvenue` et `/aurevoir` — messages + carte d'accueil personnalisables.",
            inline=False,
        )
        embed.add_field(
            name="🎭 Roles",
            value="`/autorole` — roles donnes a l'arrivee.\n"
            "`/panneaurole` — boutons pour que les membres prennent leurs roles.",
            inline=False,
        )
        embed.add_field(
            name="🛡️ Modération",
            value="`/ban` `/kick` `/mute` `/unmute` `/warn` `/warnings` `/clear` — sanctions + casier.",
            inline=False,
        )
        embed.add_field(
            name="🤖 Auto-modération & Logs",
            value="Anti-spam, anti-lien, filtre de mots + journal des évènements "
            "(configurable dans le dashboard).",
            inline=False,
        )
        embed.add_field(
            name="🛠️ Divers",
            value="`/ping` — teste la reactivite du bot.",
            inline=False,
        )
        embed.set_footer(text="D'autres modules arrivent : tickets, giveaways, niveaux, economie...")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
