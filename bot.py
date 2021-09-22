import aiohttp
import traceback

from disnake.ext import commands, tasks
import disnake

from cogs.utils import db
from cogs.utils.helpers import safe_send_prepare

initial_extensions = (
    'cogs.tags',  # cogs
    'cogs.disnake',
    'jishaku',  # community extensions
)
SLASH_COMMAND_GUILDS = (
    859290967475879966,  # m1raynee's test
    808030843078836254,  # disnake
)
async def get_prefix(bot: 'DisnakeHelper', message): 
    r = commands.when_mentioned(bot, message)
    if message.channel.id in bot.dev_channel_ids and (message.author == bot.owner or message.author in bot.owners):
        r.append('')
    return r

class DisnakeHelper(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(
            command_prefix=get_prefix,
            intents=disnake.Intents.all(),
            test_guilds=SLASH_COMMAND_GUILDS,
            **kwargs
        )
        self.startup = disnake.utils.utcnow()

        for ext in initial_extensions:
            try:
                self.load_extension(ext)
            except Exception as e:
                print(f'Could not load extension {ext} due to {e.__class__.__name__}: {e}')
        
        self.loop.run_until_complete(db.init())
        self.session = aiohttp.ClientSession(loop=self.loop)

    async def on_ready(self):
        print(f'Logged on as {self.user} (ID: {self.user.id})')
    
    async def on_slash_command_error(self, interaction: disnake.ApplicationCommandInteraction, exception: commands.CommandError) -> None:
        if not interaction.application_command.has_error_handler() or interaction.application_command.cog.has_slash_error_handler():
            now = disnake.utils.utcnow().timestamp()
            content = f'Unknown error happen. Contact m1raynee. Error timestamp: {now}'
            if interaction.response.is_done():
                await interaction.channel.send(content)
            else:
                await interaction.response.send_message(content, ephemeral=True)
            await self.owner.send(f'{now}```py\n{interaction}\n```')
            await self.owner.send(**(await safe_send_prepare(traceback.format_exception(type(exception), exception, exception.__traceback__))))
        
        # return await super().on_slash_command_error(interaction, exception)
