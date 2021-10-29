import aiohttp
import traceback

from disnake.ext import commands, tasks
import disnake

from cogs.utils import db
from cogs.utils.send import safe_send_prepare

initial_extensions = (
    'cogs.tags',  # cogs
    'cogs.disnake_only',
    'cogs.snippets',
    'cogs.reminder',
    # 'cogs.meta',
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
    def __init__(self, **kwargs):
        super().__init__(
            command_prefix=commands.when_mentioned_or('?'),
            intents=disnake.Intents.all(),
            test_guilds=SLASH_COMMAND_GUILDS,
            **kwargs
        )
        self.startup = disnake.utils.utcnow()

        for ext in initial_extensions:
            try:
                self.load_extension(ext)
            except Exception as e:
                tb = '\n'.join(traceback.format_exception(None, e, e.__traceback__))
                print(f'Could not load extension {ext} due to {e.__class__.__name__}: {e}')
                print(tb)
        
        self.loop.run_until_complete(db.init())
        self.http_session = aiohttp.ClientSession(loop=self.loop)

    async def on_ready(self):
        print(f'Logged on as {self.user} (ID: {self.user.id})')
    
    async def on_slash_command_error(self, interaction: disnake.ApplicationCommandInteraction, exception: commands.CommandError) -> None:
        if interaction.response.is_done():
            m = interaction.followup.send
        else:
            m = interaction.response.send_message

        if isinstance(exception, (RuntimeError, commands.CheckFailure)):
            return await m(exception, ephemeral=True)

        content = f'Unknown error happen. Contact m1raynee. Error timestamp: {disnake.utils.utcnow().timestamp()}'
        await m(content, ephemeral=True)
        tb = '\n'.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        await self.owner.send((
            '```py\n'
            f'{interaction.user = }\n'
            f'{interaction.channel.id = }\n'
            f'{interaction.application_command.name = }\n'
            f'{interaction.options = }\n'
            '```'
        ))
        await self.owner.send(**(await safe_send_prepare(f'```py\n{tb}\n```')))
        super().on_slash_command_error

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

    def ids(self, *id_list):
        return list(set((*id_list, *self.owner_ids)))