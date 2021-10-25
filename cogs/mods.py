from disnake.ext import commands
import disnake

from .utils.converters import FutureTime, futuretime_autocomp


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command()
    async def tempmute(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        duration: str = commands.Param(converter=FutureTime, autocomplete=futuretime_autocomp)
        ):
        ...