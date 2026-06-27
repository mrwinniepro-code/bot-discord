"""Module Giveaways : tirages au sort avec bouton de participation."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..database import Giveaway, GiveawayEntry, session_scope
from ..utils.timeparse import human_duration, parse_duration

log = logging.getLogger("bot.giveaways")


def _utcnow() -> datetime:
    """Maintenant en UTC, naif (pour coller au stockage SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GiveawayJoinView(discord.ui.View):
    """Bouton persistant 'Participer'. Identifie le giveaway via le message."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Participer", emoji="🎉",
        style=discord.ButtonStyle.primary, custom_id="gw:join",
    )
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        with session_scope() as s:
            gw = (
                s.query(Giveaway)
                .filter_by(message_id=interaction.message.id, ended=False)
                .first()
            )
            if gw is None:
                return await interaction.response.send_message(
                    "Ce giveaway est terminé.", ephemeral=True
                )
            entry = (
                s.query(GiveawayEntry)
                .filter_by(giveaway_id=gw.id, user_id=interaction.user.id)
                .first()
            )
            if entry:
                s.delete(entry)
                msg = "Tu ne participes plus à ce giveaway."
            else:
                s.add(GiveawayEntry(giveaway_id=gw.id, user_id=interaction.user.id))
                msg = "🎉 Tu participes au giveaway ! Bonne chance !"
        await interaction.response.send_message(msg, ephemeral=True)


class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(GiveawayJoinView())
        self.check_giveaways.start()

    async def cog_unload(self) -> None:
        self.check_giveaways.cancel()

    # ------------------------------------------------------------------ #
    #  Boucle de fin automatique                                          #
    # ------------------------------------------------------------------ #
    @tasks.loop(seconds=15)
    async def check_giveaways(self) -> None:
        now = _utcnow()
        with session_scope() as s:
            due = (
                s.query(Giveaway)
                .filter(Giveaway.ended == False, Giveaway.end_time <= now)  # noqa: E712
                .all()
            )
            ids = [g.id for g in due]
        for gid in ids:
            try:
                await self._end_giveaway(gid)
            except Exception:
                log.exception("Erreur en terminant le giveaway %s", gid)

    @check_giveaways.before_loop
    async def _before(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------ #
    #  Fin & tirage                                                       #
    # ------------------------------------------------------------------ #
    async def _end_giveaway(self, gw_id: int) -> list[int]:
        with session_scope() as s:
            gw = s.get(Giveaway, gw_id)
            if gw is None or gw.ended:
                return []
            gw.ended = True
            entrants = [e.user_id for e in gw.entries]
            channel_id, message_id = gw.channel_id, gw.message_id
            prize, winners_count = gw.prize, gw.winners_count

        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return []

        winners = random.sample(entrants, min(winners_count, len(entrants))) if entrants else []
        if winners:
            mentions = ", ".join(f"<@{w}>" for w in winners)
            await channel.send(
                f"🎉 Félicitations {mentions} ! Vous gagnez **{prize}** !",
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        else:
            await channel.send(f"😢 Le giveaway **{prize}** s'est terminé sans participant.")

        if message_id:
            try:
                msg = await channel.fetch_message(message_id)
                embed = msg.embeds[0] if msg.embeds else discord.Embed(title="🎉 Giveaway")
                embed.color = discord.Color.dark_grey()
                embed.add_field(
                    name="Terminé",
                    value=(", ".join(f"<@{w}>" for w in winners) if winners else "Aucun gagnant"),
                    inline=False,
                )
                await msg.edit(embed=embed, view=None)
            except discord.HTTPException:
                pass
        return winners

    # ------------------------------------------------------------------ #
    #  Commandes                                                          #
    # ------------------------------------------------------------------ #
    giveaway = app_commands.Group(
        name="giveaway",
        description="Tirages au sort",
        guild_only=True,
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @giveaway.command(name="start", description="Lance un giveaway.")
    @app_commands.describe(
        duree="Durée (ex: 1h, 2d, 30m)",
        gagnants="Nombre de gagnants",
        prix="Ce qu'il y a à gagner",
    )
    async def start(
        self,
        interaction: discord.Interaction,
        duree: str,
        gagnants: app_commands.Range[int, 1, 20],
        prix: str,
    ) -> None:
        delta = parse_duration(duree)
        if delta is None:
            return await interaction.response.send_message(
                "❌ Durée invalide. Exemples : `30m`, `2h`, `1d`.", ephemeral=True
            )
        end = _utcnow() + delta
        with session_scope() as s:
            gw = Giveaway(
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                host_id=interaction.user.id,
                prize=prix[:255],
                winners_count=gagnants,
                end_time=end,
                ended=False,
            )
            s.add(gw)
            s.flush()
            gid = gw.id

        end_aware = end.replace(tzinfo=timezone.utc)
        embed = discord.Embed(
            title="🎉 GIVEAWAY 🎉",
            description=f"**{prix}**\n\nClique sur 🎉 pour participer !",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Gagnants", value=str(gagnants), inline=True)
        embed.add_field(name="Fin", value=discord.utils.format_dt(end_aware, "R"), inline=True)
        embed.set_footer(text=f"Organisé par {interaction.user} • #{gid}")

        msg = await interaction.channel.send(embed=embed, view=GiveawayJoinView())
        with session_scope() as s:
            gw = s.get(Giveaway, gid)
            gw.message_id = msg.id
        await interaction.response.send_message(
            f"✅ Giveaway lancé pour **{human_duration(delta)}** ! (#{gid})", ephemeral=True
        )

    @giveaway.command(name="end", description="Termine un giveaway immédiatement.")
    @app_commands.describe(id="Numéro du giveaway")
    async def end(self, interaction: discord.Interaction, id: int) -> None:
        with session_scope() as s:
            gw = s.get(Giveaway, id)
            if gw is None or gw.guild_id != interaction.guild_id:
                return await interaction.response.send_message("❌ Giveaway introuvable.", ephemeral=True)
            if gw.ended:
                return await interaction.response.send_message("ℹ️ Déjà terminé.", ephemeral=True)
        await interaction.response.send_message("⏱️ Tirage en cours…", ephemeral=True)
        await self._end_giveaway(id)

    @giveaway.command(name="reroll", description="Retire un nouveau gagnant pour un giveaway terminé.")
    @app_commands.describe(id="Numéro du giveaway")
    async def reroll(self, interaction: discord.Interaction, id: int) -> None:
        with session_scope() as s:
            gw = s.get(Giveaway, id)
            if gw is None or gw.guild_id != interaction.guild_id:
                return await interaction.response.send_message("❌ Giveaway introuvable.", ephemeral=True)
            entrants = [e.user_id for e in gw.entries]
            prize = gw.prize
        if not entrants:
            return await interaction.response.send_message("❌ Aucun participant.", ephemeral=True)
        winner = random.choice(entrants)
        await interaction.response.send_message(
            f"🎉 Nouveau gagnant pour **{prize}** : <@{winner}> !",
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @giveaway.command(name="liste", description="Liste les giveaways en cours.")
    async def liste(self, interaction: discord.Interaction) -> None:
        with session_scope() as s:
            active = (
                s.query(Giveaway)
                .filter_by(guild_id=interaction.guild_id, ended=False)
                .order_by(Giveaway.end_time)
                .all()
            )
            lines = [
                f"**#{g.id}** — {g.prize} (fin "
                f"{discord.utils.format_dt(g.end_time.replace(tzinfo=timezone.utc), 'R')})"
                for g in active
            ]
        if not lines:
            return await interaction.response.send_message("Aucun giveaway en cours.", ephemeral=True)
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
