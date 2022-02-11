from __future__ import annotations
from math import log
from typing import Dict, TYPE_CHECKING, List, Tuple

from disnake.ext import commands
from disnake import (
    ui,
    ChannelType,
    ButtonStyle,
    MessageInteraction,
    Thread,
    Member,
    Embed,
    SelectOption,
    utils
)
from disnake import MessageType
from .utils.views import Confirm
from .utils.db.users import User

if TYPE_CHECKING:
    from bot import DisnakeHelper


HELPER_ROLE_ID = 907571014085525525
HelpersMapping = Dict[Member, int]

async def _get_help_reqester(thread: Thread) -> Member:
    return (await thread.history(limit=1, oldest_first=True).flatten())[0].mentions[0]

def _awerage_helpers(helpers_mapping: HelpersMapping) -> Tuple[List[Member], int]:
    message_sum = sum(helpers_mapping.values())
    awerage = message_sum // len(helpers_mapping)
    karma = log(message_sum / 5) / log(2)
    return [
        k for k, v in helpers_mapping.items()
        if v >= awerage
    ], int(karma) + 1 if karma >= .0 else 0

class KarmaChoicer(ui.Select):
    def __init__(self, helpers: HelpersMapping) -> None:
        options = [
            SelectOption(
                label=k.display_name,
                value=str(k.id),
                description=f'{v} message{"s" if v > 0 else ""}'
            )
            for k, v in sorted(helpers.items(), key=lambda p: p[1])[:25]
        ]
        super().__init__(placeholder='Select most helpful person', options=options)
        self.helpers = helpers

    async def callback(self, interaction: MessageInteraction):
        self.view.result = utils.get(self.helpers, id=int(self.values[0]))
        await interaction.response.edit_message(content=f'{self.view.result} will gain additional Karma points.', view=None)
        self.view.stop()

class CloseView(ui.View):
    def __init__(self, bot: DisnakeHelper = None):
        super().__init__(timeout=None)

        if bot is None:
            self.stop()
            return
        self.bot = bot
    
    async def interaction_check(self, interaction: MessageInteraction) -> bool:
        if not isinstance(interaction.channel, Thread):
            await interaction.response.defer()
            return False
        if interaction.channel.archived:
            await interaction.response.edit_message(view=None)
            return False
        if interaction.channel not in self.bot._requesters:
            member = await _get_help_reqester(interaction.channel)
            self.bot._requesters[interaction.channel] = member
        else:
            member = self.bot._requesters[interaction.channel]
    
        if interaction.author.id == member.id or HELPER_ROLE_ID in interaction.author._roles:
            return True
        await interaction.response.send_message(
            f'You\'re not {member} (reqester) and you don\'t have <@&{HELPER_ROLE_ID}> role',
            ephemeral=True
        )
        return False
    
    @ui.button(label='Close', style=ButtonStyle.red, custom_id='help:close')
    async def close_thread(self, button: ui.Button, interaction: MessageInteraction):
        if interaction.channel in self.bot._is_being_closing:
            return await interaction.response.send_message(
                f'Already closing by {self.bot._is_being_closing[interaction.channel]}...',
                ephemeral=True
            )
        self.bot._is_being_closing[interaction.channel] = interaction.author
        requester = self.bot._requesters[interaction.channel]
        
        await interaction.response.defer(ephemeral=True)
        helpers_mapping: HelpersMapping = {}
        async for message in interaction.channel.history(limit=None).filter(lambda m: m.author.id != requester.id and not m.author.bot):
            helpers_mapping[message.author] = helpers_mapping.get(message.author, 0) + 1
        
        initial_message = (await interaction.channel.history(limit=1, oldest_first=True).flatten())[0]
        if len(helpers_mapping) < 2:
            await interaction.channel.edit(archived=True)
            return
        else:
            karma_view = ui.View()
            karma_view.add_item(KarmaChoicer(helpers_mapping))
            msg = await interaction.followup.send(content='Counting points...', view=karma_view, ephemeral=True, wait=True)
            if await karma_view.wait():
                await msg.edit(content='no, then...', view=None)
                self.bot._is_being_closing.pop(interaction.channel)
                return
            self.bot._is_being_closing.pop(interaction.channel)
            requester_thanks = karma_view.result
        helpers, karma = _awerage_helpers(helpers_mapping)

        await interaction.channel.edit(archived=True)


class HelpButton(ui.Button['MainHelpView']):
    def __init__(self, *, help_type: str, style: ButtonStyle):
        super().__init__(style=style, label=f'{help_type} help', custom_id=f'create-help:{help_type.lower()}')
        self.help_type = help_type
    
    async def callback(self, interaction: MessageInteraction):
        confirm_view = Confirm(author_id=interaction.author.id)
        await interaction.response.send_message(f'Are you wanna create a {self.label} thread?', view=confirm_view, ephemeral=True)
        res = await confirm_view.start()

        if res is None:
            return await interaction.edit_original_message(content='uh, probably not?...', view=None)
        elif not res:
            return await interaction.edit_original_message(content='Canceled', view=None)
        await interaction.edit_original_message(content='You can dismiss this message.', view=None)

        thread = await interaction.channel.create_thread(
            name=f'{self.label} (for {interaction.author})',
            type=ChannelType.public_thread
        )
        emb = Embed(
            title=f'{interaction.author} requested {self.label}',
            description='Please describe your problem.',
            color=0x2F3136
        )
        emb.set_footer(text='See /tag show name:help for a guide to getting help')
        close_view = CloseView()
        self.view.bot._requesters[thread] = interaction.author
        m = await thread.send(f'{interaction.author.mention} \N{em dash} <@&{HELPER_ROLE_ID}>', embed=emb, view=close_view)
        await m.pin()
        await interaction.channel.purge(limit=1, check=lambda m: m.type == MessageType.thread_created)
        

class MainHelpView(ui.View):
    def __init__(self, bot: DisnakeHelper = None):
        super().__init__(timeout=None)

        self.add_item(HelpButton(help_type='Disnake', style=ButtonStyle.red))
        self.add_item(HelpButton(help_type='Dislash.py', style=ButtonStyle.green))
        self.add_item(HelpButton(help_type='Python', style=ButtonStyle.blurple))

        if bot is None:
            self.stop()
            return
        self.bot = bot


class HelpRequests(commands.Cog):
    def __init__(self, bot: DisnakeHelper):
        self.bot = bot
        bot._help_view_added = False
    
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.bot._help_view_added:
            self.bot.add_view(MainHelpView(self.bot))
            self.bot.add_view(CloseView(self.bot))
            self.bot._help_view_added = True
    
    @commands.command()
    async def send_help_view(self, ctx):
        await ctx.send('choose needed help pls', view=MainHelpView())

def setup(bot):
    bot.add_cog(HelpRequests(bot))
