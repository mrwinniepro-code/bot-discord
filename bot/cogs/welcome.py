"""Module Arrivees / Departs : messages personnalisables + carte image."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..database import get_guild_config, session_scope
from ..utils.images import generate_welcome_card

log = logging.getLogger("bot.welcome")

PLACEHOLDERS_HELP = (
    "Variables utilisables : `{user_mention}` (mention), `{user_name}` (pseudo brut), "
    "`{user}` (surnom affiche), `{server}` (nom du serveur), `{count}` (nombre de membres)."
)


def format_message(template: str, member: discord.Member) -> str:
    """Remplace les variables du modele par les vraies valeurs.

    L'ordre est important : on remplace les variables longues avant `{user}`.
    """
    guild = member.guild
    return (
        template.replace("{user_mention}", member.mention)
        .replace("{user_name}", member.name)
        .replace("{user}", member.display_name)
        .replace("{server}", guild.name)
        .replace("{count}", str(guild.member_count or 0))
    )


class Welcome(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    #  Logique d'envoi                                                    #
    # ------------------------------------------------------------------ #
    async def send_welcome(self, member: discord.Member) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, member.guild.id)
            if not cfg.welcome_enabled or not cfg.welcome_channel_id:
                return
            channel_id = cfg.welcome_channel_id
            message = cfg.welcome_message
            card_enabled = cfg.welcome_card_enabled
            card_title = cfg.welcome_card_title
            card_bg = cfg.welcome_card_background

        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        kwargs: dict = {"content": format_message(message, member)}
        if card_enabled:
            try:
                buf = await generate_welcome_card(member, title=card_title, background_path=card_bg)
                kwargs["file"] = discord.File(buf, filename="bienvenue.png")
            except Exception:
                log.exception("Echec de generation de la carte de bienvenue")

        try:
            await channel.send(**kwargs)
        except discord.Forbidden:
            log.warning("Permission manquante pour ecrire dans le salon d'arrivee (%s)", channel_id)

    async def send_leave(self, member: discord.Member) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, member.guild.id)
            if not cfg.leave_enabled or not cfg.leave_channel_id:
                return
            channel_id = cfg.leave_channel_id
            message = cfg.leave_message

        channel = member.guild.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        try:
            await channel.send(
                format_message(message, member),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.Forbidden:
            log.warning("Permission manquante pour ecrire dans le salon de depart (%s)", channel_id)

    # ------------------------------------------------------------------ #
    #  Evenements                                                         #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self.send_welcome(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        await self.send_leave(member)

    # ------------------------------------------------------------------ #
    #  Commandes : /bienvenue                                            #
    # ------------------------------------------------------------------ #
    bienvenue = app_commands.Group(
        name="bienvenue",
        description="Configurer les messages d'arrivee",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @bienvenue.command(name="salon", description="Definit le salon d'arrivee (active le module).")
    @app_commands.describe(salon="Salon ou seront postes les messages d'arrivee")
    async def bienvenue_salon(self, interaction: discord.Interaction, salon: discord.TextChannel) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.welcome_channel_id = salon.id
            cfg.welcome_enabled = True
        await interaction.response.send_message(
            f"✅ Les arrivees seront annoncees dans {salon.mention}.\n"
            f"Teste avec `/bienvenue apercu`. {PLACEHOLDERS_HELP}",
            ephemeral=True,
        )

    @bienvenue.command(name="message", description="Definit le texte du message d'arrivee.")
    @app_commands.describe(texte="Texte du message. " + PLACEHOLDERS_HELP)
    async def bienvenue_message(self, interaction: discord.Interaction, texte: str) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.welcome_message = texte
        await interaction.response.send_message(
            "✅ Message d'arrivee mis a jour. Apercu avec `/bienvenue apercu`.", ephemeral=True
        )

    @bienvenue.command(name="titre", description="Texte affiche en gros sur la carte image.")
    @app_commands.describe(texte="Ex : Bienvenue, Welcome, Salut...")
    async def bienvenue_titre(self, interaction: discord.Interaction, texte: str) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.welcome_card_title = texte[:80]
        await interaction.response.send_message("✅ Titre de la carte mis a jour.", ephemeral=True)

    @bienvenue.command(name="carte", description="Active ou desactive la carte image d'arrivee.")
    @app_commands.describe(actif="Vrai pour afficher la carte image, Faux pour seulement le texte")
    async def bienvenue_carte(self, interaction: discord.Interaction, actif: bool) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.welcome_card_enabled = actif
        await interaction.response.send_message(
            f"✅ Carte image {'activee' if actif else 'desactivee'}.", ephemeral=True
        )

    @bienvenue.command(name="apercu", description="Affiche un apercu du message d'arrivee (ici).")
    async def bienvenue_apercu(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        member = interaction.user
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            message, card_enabled = cfg.welcome_message, cfg.welcome_card_enabled
            card_title, card_bg = cfg.welcome_card_title, cfg.welcome_card_background

        kwargs: dict = {"content": format_message(message, member)}
        if card_enabled:
            try:
                buf = await generate_welcome_card(member, title=card_title, background_path=card_bg)
                kwargs["file"] = discord.File(buf, filename="bienvenue.png")
            except Exception:
                log.exception("Echec apercu carte")
        await interaction.followup.send(**kwargs)

    @bienvenue.command(name="desactiver", description="Desactive les messages d'arrivee.")
    async def bienvenue_desactiver(self, interaction: discord.Interaction) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.welcome_enabled = False
        await interaction.response.send_message("✅ Messages d'arrivee desactives.", ephemeral=True)

    # ------------------------------------------------------------------ #
    #  Commandes : /aurevoir                                             #
    # ------------------------------------------------------------------ #
    aurevoir = app_commands.Group(
        name="aurevoir",
        description="Configurer les messages de depart",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @aurevoir.command(name="salon", description="Definit le salon de depart (active le module).")
    @app_commands.describe(salon="Salon ou seront postes les messages de depart")
    async def aurevoir_salon(self, interaction: discord.Interaction, salon: discord.TextChannel) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.leave_channel_id = salon.id
            cfg.leave_enabled = True
        await interaction.response.send_message(
            f"✅ Les departs seront annonces dans {salon.mention}. {PLACEHOLDERS_HELP}",
            ephemeral=True,
        )

    @aurevoir.command(name="message", description="Definit le texte du message de depart.")
    @app_commands.describe(texte="Texte du message. " + PLACEHOLDERS_HELP)
    async def aurevoir_message(self, interaction: discord.Interaction, texte: str) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.leave_message = texte
        await interaction.response.send_message("✅ Message de depart mis a jour.", ephemeral=True)

    @aurevoir.command(name="desactiver", description="Desactive les messages de depart.")
    async def aurevoir_desactiver(self, interaction: discord.Interaction) -> None:
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.leave_enabled = False
        await interaction.response.send_message("✅ Messages de depart desactives.", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
