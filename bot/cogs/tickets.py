"""Module Tickets : panneau a bouton -> salon prive avec le staff."""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..database import Ticket, get_guild_config, session_scope

log = logging.getLogger("bot.tickets")


class OpenTicketView(discord.ui.View):
    """Bouton persistant 'Ouvrir un ticket' (sur le panneau)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ouvrir un ticket", emoji="🎫",
        style=discord.ButtonStyle.primary, custom_id="ticket:open",
    )
    async def open(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await open_ticket(interaction)


class CloseTicketView(discord.ui.View):
    """Bouton persistant 'Fermer le ticket' (dans le salon de ticket)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Fermer le ticket", emoji="🔒",
        style=discord.ButtonStyle.danger, custom_id="ticket:close",
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await close_ticket(interaction)


async def open_ticket(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    user = interaction.user
    with session_scope() as s:
        cfg = get_guild_config(s, guild.id)
        enabled = cfg.tickets_enabled
        category_id = cfg.ticket_category_id
        support_role_id = cfg.ticket_support_role_id
        open_message = cfg.ticket_open_message
        existing = (
            s.query(Ticket)
            .filter_by(guild_id=guild.id, user_id=user.id, open=True)
            .first()
        )
        existing_channel_id = None
        if existing:
            if guild.get_channel(existing.channel_id) is None:
                existing.open = False  # salon disparu -> on nettoie
            else:
                existing_channel_id = existing.channel_id

    if not enabled:
        return await interaction.response.send_message(
            "🎫 Les tickets ne sont pas activés sur ce serveur.", ephemeral=True
        )
    if existing_channel_id:
        chan = guild.get_channel(existing_channel_id)
        return await interaction.response.send_message(
            f"Tu as déjà un ticket ouvert : {chan.mention}", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    support_role = guild.get_role(support_role_id) if support_role_id else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True, read_message_history=True
        ),
        user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, attach_files=True, read_message_history=True
        ),
    }
    if support_role:
        overwrites[support_role] = discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        )

    category = guild.get_channel(category_id) if category_id else None
    if not isinstance(category, discord.CategoryChannel):
        category = None

    try:
        channel = await guild.create_text_channel(
            name=f"ticket-{user.name}"[:95],
            category=category,
            overwrites=overwrites,
            reason=f"Ticket ouvert par {user}",
        )
    except discord.Forbidden:
        return await interaction.followup.send(
            "❌ Je n'ai pas la permission de créer un salon (donne-moi *Gérer les salons*).",
            ephemeral=True,
        )

    with session_scope() as s:
        s.add(Ticket(guild_id=guild.id, channel_id=channel.id, user_id=user.id, open=True))

    embed = discord.Embed(title="🎫 Ticket", description=open_message, color=discord.Color.blurple())
    mention = user.mention + (f" {support_role.mention}" if support_role else "")
    await channel.send(
        content=mention, embed=embed, view=CloseTicketView(),
        allowed_mentions=discord.AllowedMentions(users=True, roles=True),
    )
    await interaction.followup.send(f"✅ Ton ticket a été créé : {channel.mention}", ephemeral=True)


async def close_ticket(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    channel = interaction.channel
    with session_scope() as s:
        ticket = s.query(Ticket).filter_by(guild_id=guild.id, channel_id=channel.id).first()
        if ticket is None:
            return await interaction.response.send_message(
                "Ce salon n'est pas un ticket.", ephemeral=True
            )
        opener_id = ticket.user_id
        cfg = get_guild_config(s, guild.id)
        support_role_id = cfg.ticket_support_role_id

    member = interaction.user
    is_staff = member.guild_permissions.manage_channels or (
        support_role_id is not None and any(r.id == support_role_id for r in member.roles)
    )
    if member.id != opener_id and not is_staff:
        return await interaction.response.send_message(
            "Seul l'auteur du ticket ou le staff peut le fermer.", ephemeral=True
        )

    with session_scope() as s:
        t = s.query(Ticket).filter_by(guild_id=guild.id, channel_id=channel.id).first()
        if t:
            t.open = False

    await interaction.response.send_message(
        "🔒 Ticket fermé. Le salon sera supprimé dans 5 secondes…"
    )
    await asyncio.sleep(5)
    try:
        await channel.delete(reason="Ticket fermé")
    except discord.HTTPException:
        pass


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        # Boutons a custom_id fixe : un seul enregistrement gere tous les messages
        self.bot.add_view(OpenTicketView())
        self.bot.add_view(CloseTicketView())

    ticket = app_commands.Group(
        name="ticket",
        description="Système de tickets",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @ticket.command(name="panneau", description="Crée le panneau d'ouverture de tickets dans un salon.")
    @app_commands.describe(
        salon="Salon où poster le panneau",
        titre="Titre du panneau",
        description="Texte du panneau",
    )
    async def panneau(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel,
        titre: str = "Besoin d'aide ?",
        description: str = "Clique sur le bouton ci-dessous pour ouvrir un ticket avec le staff.",
    ) -> None:
        embed = discord.Embed(title=titre[:256], description=description, color=discord.Color.blurple())
        try:
            await salon.send(embed=embed, view=OpenTicketView())
        except discord.Forbidden:
            return await interaction.response.send_message(
                f"❌ Je ne peux pas écrire dans {salon.mention}.", ephemeral=True
            )
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            cfg.tickets_enabled = True
        await interaction.response.send_message(
            f"✅ Panneau de tickets créé dans {salon.mention}. "
            "Configure la catégorie et le rôle support dans le dashboard.",
            ephemeral=True,
        )

    @ticket.command(name="fermer", description="Ferme le ticket actuel.")
    async def fermer(self, interaction: discord.Interaction) -> None:
        await close_ticket(interaction)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
