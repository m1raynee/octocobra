from disnake.ext import commands
import disnake

class Meta(commands.Cog):
    """Meta."""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
    
    @commands.slash_command()
    async def payload(
        self,
        inter: disnake.ApplicationCommandInteraction,
        integer: int,
        string: str
    ):
        """
        REsponding with command payload.
        Parameters
        ----------
        integer: int goes here
        string: str goes here
        """
        await inter.response.send_message(inter.data.options)

def setup(bot):
    bot.add_cog(Meta(bot))
