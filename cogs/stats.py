from disnake.ext import commands
import disnake

from .utils.db.stats import Commands

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._commands_cache = []

    async def bulk_stats_insert(self):
        if not self._commands_cache:
            return

        await Commands.bulk_create(self._commands_cache)
    
    async def on_slash_command(): ...