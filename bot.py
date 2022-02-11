from typing import Dict, Mapping
import aiohttp
import traceback

from disnake.ext import commands
import disnake

from cogs.utils import db
from cogs.utils.send import safe_send_prepare

initial_extensions = (
    'cogs.tags',  # cogs
    'cogs.guild_features',
    'cogs.snippets',
    'cogs.reminder',
    'cogs.mods',
    'cogs.meta',
    'jishaku',  # community extensions
)
SLASH_COMMAND_GUILDS = (
    859290967475879966,  # m1raynee's test
    808030843078836254,  # disnake
)
# async def get_prefix(bot: 'DisnakeHelper', message): 
#     r = commands.when_mentioned(bot, message)
#     if message.channel.id in bot.dev_channel_ids and (message.author == bot.owner or message.author in bot.owners):
#         r.append('')
#     return r

class DisnakeHelper(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or('?'),
            intents=disnake.Intents.all(),
            test_guilds=SLASH_COMMAND_GUILDS,
        )
        self.startup = disnake.utils.utcnow()
        self.defer_pool: Mapping[int, disnake.Interaction] = {}

        for ext in initial_extensions:
            try:
                self.load_extension(ext)
            except Exception as e:
                tb = '\n'.join(traceback.format_exception(None, e, e.__traceback__))
                print(f'Could not load extension {ext} due to {e.__class__.__name__}: {e}')
                print(tb)
        
        self.loop.run_until_complete(db.init())
        self.http_session = aiohttp.ClientSession(loop=self.loop)

        self._requesters: Dict[disnake.Thread, disnake.Member] = {}
        self._is_being_closing: Dict[disnake.Thread, disnake.Member] = {}

    async def on_ready(self):
        print(f'Logged on as {self.user} (ID: {self.user.id})')

    
    async def on_slash_command_error(self, interaction: disnake.ApplicationCommandInteraction, exception: commands.CommandError) -> None:
        exception = getattr(exception, 'original', exception)
        if isinstance(exception, (RuntimeError, commands.CheckFailure)):
            return await interaction.send(exception, ephemeral=True)

        content = f'Unknown error happen. Contact m1raynee. Error timestamp: {disnake.utils.utcnow().timestamp()}'
        await interaction.send(content, ephemeral=True)
        tb = '\n'.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        await self.owner.send((
            '```py\n'
            f'user = {interaction.user}\n'
            f'channel.id = {interaction.channel.id}\n'
            f'qualified_name = {interaction.application_command.qualified_name}\n'
            f'options = {interaction.options}\n'
            '```'
        ))
        await self.owner.send(**(await safe_send_prepare(f'```py\n{tb}\n```')))

    async def on_error(self, event_method: str, *args, **kwargs) -> None:
        await self.owner.send((
                '```py\n'
                f'{event_method = }\n'
                f'{args = }\n'
                f'{kwargs = }\n'
                '```'
            ))
        tb = traceback.format_exc()
        await self.owner.send(**(await safe_send_prepare(f'```py\n{tb}\n```')))
