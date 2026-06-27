"""Module Roles : auto-roles a l'arrivee + panneaux de roles a boutons."""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from ..database import (
    AutoRole,
    ReactionRoleEntry,
    ReactionRolePanel,
    session_scope,
)
from ..utils.checks import bot_can_manage_role, role_problem_message

log = logging.getLogger("bot.autoroles")


# --------------------------------------------------------------------------- #
#  Composants persistants (boutons de role)                                    #
# --------------------------------------------------------------------------- #
class RoleButton(discord.ui.Button):
    """Bouton qui ajoute/retire un role au membre qui clique."""

    def __init__(self, panel_id: int, role_id: int, label: str, emoji: str | None) -> None:
        parsed_emoji = None
        if emoji:
            try:
                parsed_emoji = discord.PartialEmoji.from_str(emoji)
            except Exception:
                parsed_emoji = None
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label[:80],
            emoji=parsed_emoji,
            custom_id=f"rr:{panel_id}:{role_id}",
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        role = guild.get_role(self.role_id) if guild else None
        if role is None:
            await interaction.response.send_message(
                "❌ Ce role n'existe plus.", ephemeral=True
            )
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Panneau de roles")
                await interaction.response.send_message(
                    f"➖ Role {role.mention} retire.", ephemeral=True
                )
            else:
                await member.add_roles(role, reason="Panneau de roles")
                await interaction.response.send_message(
                    f"➕ Role {role.mention} ajoute.", ephemeral=True
                )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Je n'ai pas la permission de gerer ce role "
                "(mon role doit etre au-dessus du sien).",
                ephemeral=True,
            )


class PanelView(discord.ui.View):
    """Vue persistante regroupant les boutons d'un panneau."""

    def __init__(self, panel_id: int, entries: list[ReactionRoleEntry]) -> None:
        super().__init__(timeout=None)
        for entry in entries:
            self.add_item(RoleButton(panel_id, entry.role_id, entry.label, entry.emoji))


# --------------------------------------------------------------------------- #
#  Cog                                                                          #
# --------------------------------------------------------------------------- #
class AutoRoles(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Re-enregistre les vues persistantes au demarrage (boutons toujours actifs)."""
        with session_scope() as s:
            panels = (
                s.query(ReactionRolePanel)
                .filter(ReactionRolePanel.message_id.isnot(None))
                .all()
            )
            for panel in panels:
                try:
                    self.bot.add_view(
                        PanelView(panel.id, list(panel.entries)),
                        message_id=panel.message_id,
                    )
                except Exception:
                    log.exception("Echec ré-enregistrement du panneau %s", panel.id)

    # ------------------------------------------------------------------ #
    #  Auto-role a l'arrivee                                              #
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        with session_scope() as s:
            role_ids = [
                r.role_id
                for r in s.query(AutoRole).filter_by(guild_id=member.guild.id).all()
            ]
        if not role_ids:
            return

        to_add = []
        for rid in role_ids:
            role = member.guild.get_role(rid)
            if role and bot_can_manage_role(member.guild, role):
                to_add.append(role)
        if to_add:
            try:
                await member.add_roles(*to_add, reason="Auto-role a l'arrivee")
            except discord.Forbidden:
                log.warning("Permission manquante pour l'auto-role sur %s", member.guild.id)

    # ------------------------------------------------------------------ #
    #  Commandes : /autorole                                             #
    # ------------------------------------------------------------------ #
    autorole = app_commands.Group(
        name="autorole",
        description="Roles donnes automatiquement a l'arrivee",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @autorole.command(name="ajouter", description="Ajoute un role a donner automatiquement.")
    @app_commands.describe(role="Role a attribuer a chaque nouveau membre")
    async def autorole_add(self, interaction: discord.Interaction, role: discord.Role) -> None:
        problem = role_problem_message(interaction.guild, role)
        if problem:
            await interaction.response.send_message("❌ " + problem, ephemeral=True)
            return
        with session_scope() as s:
            exists = (
                s.query(AutoRole)
                .filter_by(guild_id=interaction.guild_id, role_id=role.id)
                .first()
            )
            if exists:
                await interaction.response.send_message(
                    f"ℹ️ {role.mention} est deja un auto-role.", ephemeral=True
                )
                return
            s.add(AutoRole(guild_id=interaction.guild_id, role_id=role.id))
        await interaction.response.send_message(
            f"✅ {role.mention} sera donne a chaque arrivee.", ephemeral=True
        )

    @autorole.command(name="retirer", description="Retire un auto-role.")
    @app_commands.describe(role="Role a ne plus attribuer automatiquement")
    async def autorole_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        with session_scope() as s:
            row = (
                s.query(AutoRole)
                .filter_by(guild_id=interaction.guild_id, role_id=role.id)
                .first()
            )
            if row is None:
                await interaction.response.send_message(
                    f"ℹ️ {role.mention} n'est pas un auto-role.", ephemeral=True
                )
                return
            s.delete(row)
        await interaction.response.send_message(
            f"✅ {role.mention} retire des auto-roles.", ephemeral=True
        )

    @autorole.command(name="liste", description="Affiche les auto-roles configures.")
    async def autorole_list(self, interaction: discord.Interaction) -> None:
        with session_scope() as s:
            role_ids = [
                r.role_id
                for r in s.query(AutoRole).filter_by(guild_id=interaction.guild_id).all()
            ]
        if not role_ids:
            await interaction.response.send_message(
                "Aucun auto-role configure. Ajoute-en un avec `/autorole ajouter`.",
                ephemeral=True,
            )
            return
        mentions = [
            (interaction.guild.get_role(rid).mention
             if interaction.guild.get_role(rid) else f"`role supprime ({rid})`")
            for rid in role_ids
        ]
        await interaction.response.send_message(
            "🎭 Auto-roles : " + ", ".join(mentions), ephemeral=True
        )

    # ------------------------------------------------------------------ #
    #  Commandes : /panneaurole                                          #
    # ------------------------------------------------------------------ #
    panneaurole = app_commands.Group(
        name="panneaurole",
        description="Panneaux de roles : les membres cliquent pour obtenir un role",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @panneaurole.command(name="creer", description="Cree un panneau de roles (vide) dans un salon.")
    @app_commands.describe(
        salon="Salon ou poster le panneau",
        titre="Titre affiche en haut du panneau",
        description="Texte d'explication (optionnel)",
    )
    async def panel_create(
        self,
        interaction: discord.Interaction,
        salon: discord.TextChannel,
        titre: str,
        description: str = "",
    ) -> None:
        embed = discord.Embed(
            title=titre[:200],
            description=description or "Clique sur un bouton ci-dessous pour obtenir le role.",
            color=discord.Color.blurple(),
        )
        try:
            msg = await salon.send(embed=embed)
        except discord.Forbidden:
            await interaction.response.send_message(
                f"❌ Je ne peux pas ecrire dans {salon.mention}.", ephemeral=True
            )
            return

        with session_scope() as s:
            panel = ReactionRolePanel(
                guild_id=interaction.guild_id,
                channel_id=salon.id,
                message_id=msg.id,
                title=titre[:200],
                description=description,
            )
            s.add(panel)
            s.flush()
            pid = panel.id
        await interaction.response.send_message(
            f"✅ Panneau **#{pid}** cree dans {salon.mention}.\n"
            f"Ajoute des roles avec `/panneaurole ajouter id:{pid} role:@role`.",
            ephemeral=True,
        )

    @panneaurole.command(name="ajouter", description="Ajoute un bouton de role a un panneau.")
    @app_commands.describe(
        id="Numero du panneau (donne a la creation)",
        role="Role attribue par le bouton",
        label="Texte du bouton (par defaut : nom du role)",
        emoji="Emoji du bouton (optionnel)",
    )
    async def panel_add(
        self,
        interaction: discord.Interaction,
        id: int,
        role: discord.Role,
        label: str | None = None,
        emoji: str | None = None,
    ) -> None:
        problem = role_problem_message(interaction.guild, role)
        if problem:
            await interaction.response.send_message("❌ " + problem, ephemeral=True)
            return

        with session_scope() as s:
            panel = s.get(ReactionRolePanel, id)
            if panel is None or panel.guild_id != interaction.guild_id:
                await interaction.response.send_message(
                    "❌ Panneau introuvable sur ce serveur.", ephemeral=True
                )
                return
            if len(panel.entries) >= 25:
                await interaction.response.send_message(
                    "❌ Un panneau peut contenir au maximum 25 boutons.", ephemeral=True
                )
                return
            if any(e.role_id == role.id for e in panel.entries):
                await interaction.response.send_message(
                    f"ℹ️ {role.mention} est deja dans ce panneau.", ephemeral=True
                )
                return
            s.add(
                ReactionRoleEntry(
                    panel_id=panel.id,
                    role_id=role.id,
                    label=(label or role.name)[:80],
                    emoji=emoji,
                )
            )
            s.flush()
            s.refresh(panel)
            entries = list(panel.entries)
            channel_id, message_id = panel.channel_id, panel.message_id

        await self._refresh_panel_message(interaction.guild, id, channel_id, message_id, entries)
        await interaction.response.send_message(
            f"✅ {role.mention} ajoute au panneau #{id}.", ephemeral=True
        )

    @panneaurole.command(name="liste", description="Liste les panneaux de roles du serveur.")
    async def panel_list(self, interaction: discord.Interaction) -> None:
        with session_scope() as s:
            panels = s.query(ReactionRolePanel).filter_by(guild_id=interaction.guild_id).all()
            lines = []
            for p in panels:
                salon = interaction.guild.get_channel(p.channel_id)
                salon_txt = salon.mention if salon else "salon supprime"
                lines.append(f"**#{p.id}** — {p.title} ({salon_txt}, {len(p.entries)} role(s))")
        if not lines:
            await interaction.response.send_message(
                "Aucun panneau. Cree-en un avec `/panneaurole creer`.", ephemeral=True
            )
            return
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @panneaurole.command(name="supprimer", description="Supprime un panneau (et son message).")
    @app_commands.describe(id="Numero du panneau a supprimer")
    async def panel_delete(self, interaction: discord.Interaction, id: int) -> None:
        with session_scope() as s:
            panel = s.get(ReactionRolePanel, id)
            if panel is None or panel.guild_id != interaction.guild_id:
                await interaction.response.send_message(
                    "❌ Panneau introuvable sur ce serveur.", ephemeral=True
                )
                return
            channel_id, message_id = panel.channel_id, panel.message_id
            s.delete(panel)

        channel = interaction.guild.get_channel(channel_id)
        if channel and message_id:
            try:
                msg = await channel.fetch_message(message_id)
                await msg.delete()
            except discord.HTTPException:
                pass
        await interaction.response.send_message(f"✅ Panneau #{id} supprime.", ephemeral=True)

    # ------------------------------------------------------------------ #
    #  Helper                                                             #
    # ------------------------------------------------------------------ #
    async def _refresh_panel_message(
        self,
        guild: discord.Guild,
        panel_id: int,
        channel_id: int,
        message_id: int | None,
        entries: list[ReactionRoleEntry],
    ) -> None:
        """Re-edite le message du panneau avec les boutons a jour."""
        if not message_id:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(message_id)
            view = PanelView(panel_id, entries)
            self.bot.add_view(view, message_id=message_id)
            await msg.edit(view=view)
        except discord.HTTPException:
            log.warning("Impossible d'editer le message du panneau %s", panel_id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoRoles(bot))
