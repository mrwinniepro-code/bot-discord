"""Module Economie : monnaie virtuelle, daily, travail, dons, boutique de roles."""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

from ..database import ShopItem, UserEconomy, get_guild_config, session_scope
from ..utils.checks import bot_can_manage_role, role_problem_message

log = logging.getLogger("bot.economy")

DAILY_COOLDOWN = timedelta(hours=24)
WORK_COOLDOWN = timedelta(hours=1)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _currency(self, guild_id: int) -> tuple[bool, str, str]:
        with session_scope() as s:
            cfg = get_guild_config(s, guild_id)
            return cfg.economy_enabled, cfg.currency_name, cfg.currency_symbol

    @staticmethod
    def _get_account(s, guild_id: int, user_id: int) -> UserEconomy:
        acc = s.get(UserEconomy, (guild_id, user_id))
        if acc is None:
            acc = UserEconomy(guild_id=guild_id, user_id=user_id, balance=0)
            s.add(acc)
            s.flush()
        return acc

    async def _check_enabled(self, interaction: discord.Interaction) -> bool:
        enabled, _, _ = self._currency(interaction.guild_id)
        if not enabled:
            await interaction.response.send_message(
                "💰 L'économie n'est pas activée sur ce serveur (à configurer dans le dashboard).",
                ephemeral=True,
            )
        return enabled

    # ------------------------------------------------------------------ #
    #  Commandes                                                          #
    # ------------------------------------------------------------------ #
    @app_commands.command(name="solde", description="Affiche ton solde (ou celui d'un membre).")
    @app_commands.describe(membre="Membre dont voir le solde (optionnel)")
    @app_commands.guild_only()
    async def solde(self, interaction: discord.Interaction, membre: discord.Member | None = None) -> None:
        if not await self._check_enabled(interaction):
            return
        member = membre or interaction.user
        _, name, symbol = self._currency(interaction.guild_id)
        with session_scope() as s:
            acc = self._get_account(s, interaction.guild_id, member.id)
            balance = acc.balance
        await interaction.response.send_message(
            f"{symbol} **{member.display_name}** possède **{balance}** {name}."
        )

    @app_commands.command(name="daily", description="Récupère ta récompense quotidienne.")
    @app_commands.guild_only()
    async def daily(self, interaction: discord.Interaction) -> None:
        if not await self._check_enabled(interaction):
            return
        _, name, symbol = self._currency(interaction.guild_id)
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            amount = cfg.daily_amount
            acc = self._get_account(s, interaction.guild_id, interaction.user.id)
            now = _utcnow()
            if acc.last_daily and now - acc.last_daily < DAILY_COOLDOWN:
                remaining = DAILY_COOLDOWN - (now - acc.last_daily)
                hrs = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                return await interaction.response.send_message(
                    f"⏳ Tu as déjà récupéré ton daily. Reviens dans **{hrs}h{mins:02d}**.",
                    ephemeral=True,
                )
            acc.balance += amount
            acc.last_daily = now
            new_balance = acc.balance
        await interaction.response.send_message(
            f"{symbol} Tu as reçu **{amount}** {name} ! Nouveau solde : **{new_balance}**."
        )

    @app_commands.command(name="travailler", description="Travaille pour gagner un peu d'argent.")
    @app_commands.guild_only()
    async def travailler(self, interaction: discord.Interaction) -> None:
        if not await self._check_enabled(interaction):
            return
        _, name, symbol = self._currency(interaction.guild_id)
        with session_scope() as s:
            cfg = get_guild_config(s, interaction.guild_id)
            lo, hi = cfg.work_min, max(cfg.work_min, cfg.work_max)
            acc = self._get_account(s, interaction.guild_id, interaction.user.id)
            now = _utcnow()
            if acc.last_work and now - acc.last_work < WORK_COOLDOWN:
                remaining = WORK_COOLDOWN - (now - acc.last_work)
                mins = int(remaining.total_seconds() // 60) + 1
                return await interaction.response.send_message(
                    f"⏳ Tu es fatigué. Reviens travailler dans **{mins} min**.", ephemeral=True
                )
            earned = random.randint(lo, hi)
            acc.balance += earned
            acc.last_work = now
            new_balance = acc.balance
        jobs = ["livré des pizzas", "codé un bot", "promené des chiens", "vendu des cookies", "fait le ménage"]
        await interaction.response.send_message(
            f"💼 Tu as {random.choice(jobs)} et gagné **{earned}** {name} {symbol} ! "
            f"Solde : **{new_balance}**."
        )

    @app_commands.command(name="donner", description="Donne de l'argent à un membre.")
    @app_commands.describe(membre="À qui donner", montant="Combien donner")
    @app_commands.guild_only()
    async def donner(
        self, interaction: discord.Interaction, membre: discord.Member, montant: app_commands.Range[int, 1, None]
    ) -> None:
        if not await self._check_enabled(interaction):
            return
        if membre.bot or membre.id == interaction.user.id:
            return await interaction.response.send_message(
                "❌ Choisis un autre membre.", ephemeral=True
            )
        _, name, symbol = self._currency(interaction.guild_id)
        with session_scope() as s:
            sender = self._get_account(s, interaction.guild_id, interaction.user.id)
            if sender.balance < montant:
                return await interaction.response.send_message(
                    f"❌ Solde insuffisant (tu as **{sender.balance}** {name}).", ephemeral=True
                )
            receiver = self._get_account(s, interaction.guild_id, membre.id)
            sender.balance -= montant
            receiver.balance += montant
        await interaction.response.send_message(
            f"{symbol} {interaction.user.mention} a donné **{montant}** {name} à {membre.mention} !"
        )

    @app_commands.command(name="boutique", description="Affiche la boutique de rôles.")
    @app_commands.guild_only()
    async def boutique(self, interaction: discord.Interaction) -> None:
        if not await self._check_enabled(interaction):
            return
        _, name, symbol = self._currency(interaction.guild_id)
        with session_scope() as s:
            items = (
                s.query(ShopItem)
                .filter_by(guild_id=interaction.guild_id)
                .order_by(ShopItem.price)
                .all()
            )
            rows = [(it.id, it.name, it.role_id, it.price) for it in items]
        if not rows:
            return await interaction.response.send_message(
                "🛒 La boutique est vide pour le moment.", ephemeral=True
            )
        embed = discord.Embed(title="🛒 Boutique", color=discord.Color.green())
        for iid, iname, role_id, price in rows:
            role = interaction.guild.get_role(role_id)
            role_txt = role.mention if role else "(rôle supprimé)"
            embed.add_field(
                name=f"#{iid} — {iname}",
                value=f"{role_txt} • **{price}** {name} {symbol}\n`/acheter id:{iid}`",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="acheter", description="Achète un rôle dans la boutique.")
    @app_commands.describe(id="Numéro de l'article (voir /boutique)")
    @app_commands.guild_only()
    async def acheter(self, interaction: discord.Interaction, id: int) -> None:
        if not await self._check_enabled(interaction):
            return
        _, name, symbol = self._currency(interaction.guild_id)
        with session_scope() as s:
            item = s.get(ShopItem, id)
            if item is None or item.guild_id != interaction.guild_id:
                return await interaction.response.send_message("❌ Article introuvable.", ephemeral=True)
            role_id, price, iname = item.role_id, item.price, item.name

        role = interaction.guild.get_role(role_id)
        if role is None:
            return await interaction.response.send_message(
                "❌ Le rôle associé n'existe plus.", ephemeral=True
            )
        if role in interaction.user.roles:
            return await interaction.response.send_message(
                "ℹ️ Tu possèdes déjà ce rôle.", ephemeral=True
            )
        problem = role_problem_message(interaction.guild, role)
        if problem:
            return await interaction.response.send_message(
                "❌ Je ne peux pas te donner ce rôle : " + problem, ephemeral=True
            )

        with session_scope() as s:
            acc = self._get_account(s, interaction.guild_id, interaction.user.id)
            if acc.balance < price:
                return await interaction.response.send_message(
                    f"❌ Il te manque **{price - acc.balance}** {name} pour cet achat.", ephemeral=True
                )
            acc.balance -= price
            new_balance = acc.balance

        try:
            await interaction.user.add_roles(role, reason=f"Achat boutique : {iname}")
        except discord.Forbidden:
            # remboursement si l'attribution echoue
            with session_scope() as s:
                acc = self._get_account(s, interaction.guild_id, interaction.user.id)
                acc.balance += price
            return await interaction.response.send_message(
                "❌ Je n'ai pas pu te donner le rôle (tu as été remboursé).", ephemeral=True
            )
        await interaction.response.send_message(
            f"✅ Tu as acheté **{iname}** ({role.mention}) ! Solde restant : **{new_balance}** {name} {symbol}."
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
