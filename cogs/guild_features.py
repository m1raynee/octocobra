from __future__ import annotations
from typing import TYPE_CHECKING

from disnake.ext import commands
from disnake.utils import oauth_url
from disnake import (
    ApplicationCommandInteraction,
    Embed,
    User,
    Object,
    Colour,
    RawReactionActionEvent,
    Member
)
import disnake

from .utils.emojis import choice_marks
from .utils.views import Confirm
from .utils.converters import UserCondition

if TYPE_CHECKING:
    from bot import DisnakeHelper

DISNAKE_GUILD_ID = 808030843078836254
DISNAKE_BOT_ROLE = 888451879753904138
DISNAKE_ADDBOT_CHANNEL = 808032994668576829
DISNAKE_MODS = (301295716066787332, 428483942329614336)

UPDATES_ROLE = 875141786799079474
NEWS_ROLE = 875141841991893003

options = {
    UPDATES_ROLE: disnake.SelectOption(
        label='Updates', value=str(UPDATES_ROLE), description='Disnake library updates'
    ),
    NEWS_ROLE: disnake.SelectOption(
        label='News', value=str(NEWS_ROLE), description='Community and library news'
    )
}

class NotificationsView(disnake.ui.View):
    def __init__(self, bot: DisnakeHelper = None, member: disnake.Member = None):
        super().__init__(timeout=None)

        if bot is None:
            for role_id, opt in (opts:=options.copy()).items():
                if role_id in member._roles:
                    opt.default = True

            self.select_role.options = list(opts.values())
            self.stop()
        self.bot = bot
    
    @disnake.ui.select(
        placeholder='Select roles',
        custom_id='feats:select-role',
        min_values=0, max_values=2,
        options=list(options.values())
    )
    async def select_role(self, select: disnake.ui.Select, interaction: disnake.MessageInteraction):
        roles = [role_id for role_id in interaction.author._roles if role_id not in (UPDATES_ROLE, NEWS_ROLE)]
        for value in select.values:
            roles.append(disnake.Object(int(value)))
        await interaction.author.edit(roles=roles)
        await interaction.response.edit_message(content="Your roles:"', '.join([f'<@{i}>' for i in select.values]))

class Disnake(commands.Cog, name='disnake'):
    """Docs and other disnake's guild things."""

    def __init__(self, bot: DisnakeHelper):
        self.bot = bot
        self.notification_view = None
        self.persistant_added = False
    
    async def cog_load(self) -> None:
        if not self.persistant_added:
            self.notification_view = view = NotificationsView(self.bot)
            self.bot.add_view(view)
    
    def cog_unload(self) -> None:
        self.notification_view.stop()

    @commands.slash_command()
    async def addbot(
        self,
        inter: ApplicationCommandInteraction,
        bot_id: str = commands.param(converter=UserCondition(bot=True)),
        reason: str = commands.param()
    ):
        """
        Requests your bot to be added to the server.
        Parameters
        ----------
        bot_id: Bot user id
        reason: Why you want your bot here?
        """
        bot: User = bot_id


        view = Confirm(author_id=inter.author.id)
        await inter.response.send_message(
            f'You\'re going to add {bot} on this server.\n'
            'To agree, please press "Confirm" button',
            view = view
        )
        v = await view.start()

        if v is None:
            content = 'You took too long.'
        elif v:
            content = 'You will get a DM regarding the status of your bot, so make sure you have them on.'
        else:
            content = 'Canceled'
        await inter.edit_original_message(content=content, view=None)
        if not v:
            return

        g = Object(DISNAKE_GUILD_ID)
        slash_url = oauth_url(bot.id, guild=g, scopes=('bot', 'applications.commands'))
        bot_url = oauth_url(bot.id, guild=g)

        e = Embed(description=reason, color=Colour.orange())
        e.set_author(name=inter.author.display_name, icon_url=inter.author.display_avatar)
        e.set_thumbnail(url=bot.display_avatar)
        e.add_field(name='Name', value=str(bot))
        e.add_field(name='Link', value=f'[Invite URL]({bot_url})\n([with app commands]({slash_url}))')
        e.add_field(name='ID', value=bot.id, inline=False)
        e.add_field(name='Author ID', value=inter.author.id)

        msg = await self.bot.get_partial_messageable(DISNAKE_ADDBOT_CHANNEL).send(embed=e)
        for r in choice_marks:
            await msg.add_reaction(r)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: RawReactionActionEvent):
        if payload.channel_id != DISNAKE_ADDBOT_CHANNEL:
            return
        if not (payload.member and payload.member.guild_permissions.manage_guild):
            return
        if payload.user_id == self.bot.user.id:
            return

        message = await self.bot.get_channel(DISNAKE_ADDBOT_CHANNEL).fetch_message(payload.message_id)
        if message.author.id != self.bot.user.id:
            return

        if (
            payload.emoji.id in (892770746013724683, 892770746034704384)
            and len(message.embeds) != 0
            and (embed := message.embeds[0]).colour == Colour.orange()
        ):
            embed.add_field(name='Responding admin', value=f'<@{payload.user_id}>')
            bot_id = int(embed.fields[2].value)
            member_id = int(embed.fields[3].value)
            if payload.emoji.id == 892770746013724683:
                embed.colour = Colour.green()
                user_content = f'Your bot <@{bot_id}> was invited to disnake server.'
                add_content = f'<@{member_id}> will be aware about adding a bot.'
            else:
                embed.colour = Colour.red()
                user_content = f'<@{bot_id}>\'s invitation was rejected.'
                add_content = f'<@{member_id}> will be aware about rejecting a bot.'
            await message.edit(content=add_content, embed=embed)
            await message.clear_reactions()

            await (await self.bot.get_or_fetch_user(member_id)).send(user_content)
    
    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        if member.guild.id != DISNAKE_GUILD_ID:
            return
        if not member.bot:
            return

        await member.add_roles(Object(DISNAKE_BOT_ROLE))
    
    @commands.slash_command()
    async def notifications(self, inter: ApplicationCommandInteraction):
        """Edit your notifications roles"""

        await inter.send(
            'Choose which notification roles you want to get',
            view=NotificationsView(member=inter.author), ephemeral=True
        )


def setup(bot):
    bot.add_cog(Disnake(bot))
