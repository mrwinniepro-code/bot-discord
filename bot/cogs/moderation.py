"""Module Moderation : ban, kick, mute (timeout), warn, casier, clear."""
from __future__ import annotations

import logging
from datetime import timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ..database import ModCase, session_scope
from ..utils.checks import moderation_problem
from ..utils.modlog import ACTION_LABELS, moderation_embed, send_log
from ..utils.timeparse import human_duration, parse_duration

log = logging.getLogger("bot.moderation")

MAX_TIMEOUT = timedelta(days=28)  # limite Discord


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _record_case(self, guild_id, user_id, moderator_id, action, reason) -> int:
        with session_scope() as s:
            case = ModCase(
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=moderator_id,
                action=action,
                reason=reason or "",
            )
            s.add(case)
            s.flush()
            return case.id

    async def _notify_and_log(self, interaction, target, action, reason, extra=None) -> int:
        case_id = self._record_case(
            interaction.guild.id, target.id, interaction.user.id, action, reason
        )
        # DM a la cible (best effort)
        try:
            await target.send(
                f"Tu as reçu : **{ACTION_LABELS.get(action, action)}** sur "
                f"**{interaction.guild.name}**.\n> Raison : {reason or 'Aucune raison fournie'}"
            )
        except (discord.Forbidden, discord.HTTPException):
            pass
        embed = moderation_embed(action, target, interaction.user, reason, case_id=case_id, extra=extra)
        await send_log(self.bot, interaction.guild, embed, category="moderation")
        return case_id

    # ------------------------------------------------------------------ #
    #  Commandes                                                          #
    # ------------------------------------------------------------------ #
    @app_commands.command(name="ban", description="Bannit un membre du serveur.")
    @app_commands.describe(membre="Membre a bannir", raison="Raison du bannissement")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "") -> None:
        problem = moderation_problem(interaction.user, membre, interaction.guild.me)
        if problem:
            return await interaction.response.send_message("❌ " + problem, ephemeral=True)
        try:
            await interaction.guild.ban(membre, reason=f"{interaction.user} : {raison}", delete_message_seconds=0)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        cid = await self._notify_and_log(interaction, membre, "ban", raison)
        await interaction.response.send_message(f"🔨 **{membre}** banni. (dossier #{cid})")

    @app_commands.command(name="unban", description="Debannit un utilisateur par son ID.")
    @app_commands.describe(user_id="Identifiant de l'utilisateur a debannir", raison="Raison")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str, raison: str = "") -> None:
        try:
            uid = int(user_id)
        except ValueError:
            return await interaction.response.send_message("❌ ID invalide.", ephemeral=True)
        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=f"{interaction.user} : {raison}")
        except discord.NotFound:
            return await interaction.response.send_message("❌ Cet utilisateur n'est pas banni.", ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        cid = await self._notify_and_log(interaction, user, "unban", raison)
        await interaction.response.send_message(f"♻️ **{user}** debanni. (dossier #{cid})")

    @app_commands.command(name="kick", description="Expulse un membre du serveur.")
    @app_commands.describe(membre="Membre a expulser", raison="Raison de l'expulsion")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "") -> None:
        problem = moderation_problem(interaction.user, membre, interaction.guild.me)
        if problem:
            return await interaction.response.send_message("❌ " + problem, ephemeral=True)
        # DM avant l'expulsion (sinon le bot ne partage plus de serveur)
        cid = await self._notify_and_log(interaction, membre, "kick", raison)
        try:
            await membre.kick(reason=f"{interaction.user} : {raison}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        await interaction.response.send_message(f"👢 **{membre}** expulse. (dossier #{cid})")

    @app_commands.command(name="mute", description="Rend un membre muet pour une duree (ex: 10m, 1h, 1d).")
    @app_commands.describe(membre="Membre a rendre muet", duree="Duree (ex: 30m, 2h, 1d)", raison="Raison")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def mute(self, interaction: discord.Interaction, membre: discord.Member, duree: str, raison: str = "") -> None:
        problem = moderation_problem(interaction.user, membre, interaction.guild.me)
        if problem:
            return await interaction.response.send_message("❌ " + problem, ephemeral=True)
        delta = parse_duration(duree)
        if delta is None:
            return await interaction.response.send_message(
                "❌ Duree invalide. Exemples : `30m`, `2h`, `1d`, `1h30m`.", ephemeral=True
            )
        if delta > MAX_TIMEOUT:
            return await interaction.response.send_message(
                "❌ Duree maximale : 28 jours.", ephemeral=True
            )
        try:
            await membre.timeout(delta, reason=f"{interaction.user} : {raison}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        cid = await self._notify_and_log(
            interaction, membre, "mute", raison, extra=f"Duree : {human_duration(delta)}"
        )
        await interaction.response.send_message(
            f"🔇 **{membre}** rendu muet pour **{human_duration(delta)}**. (dossier #{cid})"
        )

    @app_commands.command(name="unmute", description="Retire le mute d'un membre.")
    @app_commands.describe(membre="Membre a demuter", raison="Raison")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def unmute(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "") -> None:
        if not membre.is_timed_out():
            return await interaction.response.send_message("ℹ️ Ce membre n'est pas muet.", ephemeral=True)
        try:
            await membre.timeout(None, reason=f"{interaction.user} : {raison}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        cid = await self._notify_and_log(interaction, membre, "unmute", raison)
        await interaction.response.send_message(f"🔊 **{membre}** n'est plus muet. (dossier #{cid})")

    @app_commands.command(name="warn", description="Donne un avertissement a un membre.")
    @app_commands.describe(membre="Membre a avertir", raison="Raison de l'avertissement")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, membre: discord.Member, raison: str = "") -> None:
        problem = moderation_problem(interaction.user, membre, interaction.guild.me)
        if problem:
            return await interaction.response.send_message("❌ " + problem, ephemeral=True)
        cid = await self._notify_and_log(interaction, membre, "warn", raison)
        with session_scope() as s:
            count = s.query(ModCase).filter_by(
                guild_id=interaction.guild.id, user_id=membre.id, action="warn"
            ).count()
        await interaction.response.send_message(
            f"⚠️ **{membre}** averti. (dossier #{cid}, {count} avertissement(s) au total)"
        )

    @app_commands.command(name="warnings", description="Affiche le casier d'un membre.")
    @app_commands.describe(membre="Membre dont voir le casier")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def warnings(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        with session_scope() as s:
            cases = (
                s.query(ModCase)
                .filter_by(guild_id=interaction.guild.id, user_id=membre.id)
                .order_by(ModCase.created_at.desc())
                .limit(15)
                .all()
            )
            rows = [(c.id, c.action, c.reason, c.created_at) for c in cases]
        if not rows:
            return await interaction.response.send_message(
                f"✅ **{membre}** n'a aucun dossier.", ephemeral=True
            )
        embed = discord.Embed(title=f"Casier de {membre}", color=discord.Color.orange())
        for cid, action, reason, created in rows:
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            ts = discord.utils.format_dt(created, style="R") if created else ""
            embed.add_field(
                name=f"#{cid} — {ACTION_LABELS.get(action, action)}",
                value=f"{reason or 'Aucune raison'} {ts}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="delwarn", description="Supprime un dossier du casier par son numero.")
    @app_commands.describe(dossier="Numero du dossier a supprimer")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    async def delwarn(self, interaction: discord.Interaction, dossier: int) -> None:
        with session_scope() as s:
            case = s.get(ModCase, dossier)
            if case is None or case.guild_id != interaction.guild.id:
                return await interaction.response.send_message("❌ Dossier introuvable.", ephemeral=True)
            s.delete(case)
        await interaction.response.send_message(f"🗑️ Dossier #{dossier} supprime.", ephemeral=True)

    @app_commands.command(name="clear", description="Supprime un nombre de messages dans ce salon.")
    @app_commands.describe(nombre="Nombre de messages a supprimer (1-200)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, nombre: app_commands.Range[int, 1, 200]) -> None:
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("❌ Salon non supporte.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=nombre)
        await interaction.followup.send(f"🧹 {len(deleted)} message(s) supprime(s).", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
