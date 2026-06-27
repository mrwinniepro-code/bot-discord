"""Point d'entree du bot Discord."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from .config import DEV_GUILD_ID, DISCORD_TOKEN
from .database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")

# Liste des modules (cogs) charges au demarrage.
INITIAL_COGS = [
    "bot.cogs.general",
    "bot.cogs.welcome",
    "bot.cogs.autoroles",
    "bot.cogs.moderation",
    "bot.cogs.automod",
    "bot.cogs.logs",
    "bot.cogs.tickets",
    "bot.cogs.giveaways",
    "bot.cogs.polls",
]


class DraftCloneBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True            # requis : arrivees/departs, infos membres
        intents.message_content = True    # requis plus tard : automod, XP par message
        super().__init__(
            command_prefix=commands.when_mentioned,  # on utilise surtout les slash-commands
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self) -> None:
        # 1) Base de donnees prete
        init_db()

        # 2) Chargement des modules
        for ext in INITIAL_COGS:
            try:
                await self.load_extension(ext)
                log.info("Module charge : %s", ext)
            except Exception:
                log.exception("Echec du chargement de %s", ext)

        # 3) Synchronisation des commandes slash
        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Commandes slash synchronisees sur le serveur de test %s", DEV_GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Commandes slash synchronisees globalement (peut prendre ~1h la 1ere fois)")

    async def on_ready(self) -> None:
        log.info("Connecte en tant que %s (id=%s)", self.user, self.user.id)
        log.info("Present sur %d serveur(s)", len(self.guilds))
        try:
            await self.change_presence(activity=discord.Game(name="/aide"))
        except Exception:
            pass


def main() -> None:
    if not DISCORD_TOKEN:
        raise SystemExit(
            "\n[ERREUR] Aucun token trouve.\n"
            "1) Copie le fichier .env.example en .env\n"
            "2) Mets ton token dans DISCORD_TOKEN\n"
        )

    bot = DraftCloneBot()
    try:
        bot.run(DISCORD_TOKEN, log_handler=None)
    except discord.LoginFailure:
        raise SystemExit(
            "\n[ERREUR] Token invalide. Verifie DISCORD_TOKEN dans le fichier .env.\n"
        )
    except discord.PrivilegedIntentsRequired:
        raise SystemExit(
            "\n[ERREUR] Intents privilegies non actives.\n"
            "Va sur https://discord.com/developers/applications > ton appli > Bot,\n"
            "et ACTIVE les deux interrupteurs :\n"
            "   - SERVER MEMBERS INTENT\n"
            "   - MESSAGE CONTENT INTENT\n"
        )


if __name__ == "__main__":
    main()
