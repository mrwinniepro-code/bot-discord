"""Petits utilitaires de permissions / hierarchie de roles."""
from __future__ import annotations

import discord


def bot_can_manage_role(guild: discord.Guild, role: discord.Role) -> bool:
    """Le bot peut-il attribuer/retirer ce role ?

    - pas le role @everyone
    - pas un role gere par une integration (bot, boost, etc.)
    - le role doit etre EN DESSOUS du role le plus haut du bot
    - le bot doit avoir la permission "Gerer les roles"
    """
    me = guild.me
    if me is None:
        return False
    if role.is_default() or role.managed:
        return False
    if not me.guild_permissions.manage_roles:
        return False
    return role < me.top_role


def role_problem_message(guild: discord.Guild, role: discord.Role) -> str | None:
    """Retourne un message d'erreur lisible si le role n'est pas gerable, sinon None."""
    me = guild.me
    if role.is_default():
        return "Impossible d'utiliser le role @everyone."
    if role.managed:
        return f"Le role {role.mention} est gere automatiquement (bot/boost) et ne peut pas etre attribue."
    if me is not None and not me.guild_permissions.manage_roles:
        return "Je n'ai pas la permission **Gerer les roles**. Active-la dans les parametres du serveur."
    if me is not None and role >= me.top_role:
        return (
            f"Le role {role.mention} est **au-dessus** de mon role le plus haut. "
            "Monte mon role au-dessus de lui dans Parametres du serveur > Roles."
        )
    return None


def moderation_problem(
    actor: discord.Member, target: discord.Member, me: discord.Member
) -> str | None:
    """Verifie qu'une action de moderation est legitime. Retourne une erreur ou None."""
    guild = target.guild
    if target.id == actor.id:
        return "Tu ne peux pas te cibler toi-meme."
    if target.id == me.id:
        return "Je ne peux pas me sanctionner moi-meme. 🙂"
    if target.id == guild.owner_id:
        return "Impossible de sanctionner le proprietaire du serveur."
    # L'auteur doit etre au-dessus de la cible (sauf s'il est proprietaire)
    if actor.id != guild.owner_id and target.top_role >= actor.top_role:
        return "Cette personne a un role superieur ou egal au tien."
    # Le bot doit etre au-dessus de la cible
    if target.top_role >= me.top_role:
        return "Je ne peux pas agir : son role est au-dessus (ou egal a) du mien."
    return None
