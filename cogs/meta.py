import unicodedata

from disnake.ext import commands
import disnake


def to_string(c, *, for_autocomp=False):
    digit = f'{ord(c):x}'
    name = unicodedata.name(c, 'Name not found.')
    border = "" if for_autocomp else "`"
    r = f'{border}\\U{digit:>08}{border}: {name} - {c}'
    if not for_autocomp:
        r += f' \N{EM DASH} <http://www.fileformat.info/info/unicode/char/{digit}>'
    return r

async def charinfo_autocomp(inter, value):
    if len(value) > 25:
        return {'Only up to 25 characters at a time.': ''}
    return {
        to_string(c, for_autocomp=True): value
        for c in value
    }

class Meta(commands.Cog):
    """Meta"""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
    
    @commands.slash_command()
    async def charinfo(self, inter: disnake.ApplicationCommandInteraction,
        characters: str = commands.Param(autocomplete=charinfo_autocomp)
    ):
        """
        Shows you information about a number of characters.
        Parameters
        ----------
        characters: Unicode characters you're requesting information about
        """
        if not len(characters):
            return inter.response.send_message('Nothing to display.', ephemeral=True)

        msg = '\n'.join(map(to_string, characters))
        if len(msg) > 2000:
            return await inter.response.send_message('Output too long to display.', ephemeral=True)
        await inter.response.send_message(msg, ephemeral=True)
        

def setup(bot):
    bot.add_cog(Meta(bot))
