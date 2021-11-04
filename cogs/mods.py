from __future__ import annotations
from typing import TYPE_CHECKING, Optional

from disnake.ext import commands
import disnake

from .utils.converters import ActionReason, FutureTime, futuretime_autocomp, action_autocomp
from .utils import time

if TYPE_CHECKING:
    from bot import DisnakeHelper
    from .reminder import Reminder, Timer

DISNAKE_GUILD_ID = 808030843078836254
MUTE_ROLE_ID = 902791187432370176

class Moderation(commands.Cog):
    def __init__(self, bot: DisnakeHelper):
        self.bot = bot

    @commands.slash_command(default_permission=False)
    async def mute(*_):
        pass

    @mute.sub_command(name='temp')
    async def mute_temporally(
        self,
        inter: disnake.ApplicationCommandInteraction,
        member: disnake.Member,
        duration = commands.Param(converter=FutureTime, autocomplete=futuretime_autocomp),
        reason = commands.Param(..., converter=ActionReason, autocomplete=action_autocomp)
    ):
        """
        Temporally mutes a member for the specified duration.
        Parameters
        ----------
        member: Targeted member
        duration: Time to mute member
        reason: The reason of the mute
        """
        reminder: Optional[Reminder] = self.bot.get_cog('Reminder')

        if not reminder:
            return inter.response.send_message(
                'Sorry, but this stuff is not available now. Ask m1raynee or/and try later?',
                ephemeral=True
            )
        if reason is None:
            f'Action done by {inter.author} (ID: {inter.author.id})'

        try:
            await member.add_roles(disnake.Object(MUTE_ROLE_ID), reason=reason)
        except disnake.HTTPException:
            return await inter.response.send_message(f'{member.mention} already muted.', ephemeral=True)

        await reminder.create_timer(
            duration.dt, 'tempmute', inter.author.id, member.id,
            created = inter.created_at
        )
        await inter.response.send_message(
            f'Muted {disnake.utils.escape_mentions(str(member))} '
            f'for {time.format_relative(duration.dt)}'
        )

    @commands.Cog.listener()
    async def on_tempmute_timer_complete(self, timer: Timer):
        member_id = timer.args[0]
        mod_id = timer.author_id
        await self.bot.wait_until_ready()

        guild = self.bot.get_guild(DISNAKE_GUILD_ID)
        member = await guild.get_or_fetch_member(member_id)

        if member is None or not member._roles.has(MUTE_ROLE_ID):
            # already did that
            return

        if mod_id != member_id:
            moderator = await self.bot.get_or_fetch_member(guild, mod_id)
            if moderator is None:
                try:
                    moderator = await self.bot.fetch_user(mod_id)
                except:
                    # request failed somehow
                    moderator = f'Mod ID {mod_id}'
                else:
                    moderator = f'{moderator} (ID: {mod_id})'
            else:
                moderator = f'{moderator} (ID: {mod_id})'

            reason = f'Automatic unmute from timer made on {timer.created_at} by {moderator}.'
        else:  # selfmute
            reason = f'Expiring self-mute made on {timer.created_at} by {member}'

        try:
            await member.remove_roles(disnake.Object(id=MUTE_ROLE_ID), reason=reason)
        except disnake.HTTPException:
            pass

def setup(bot):
    bot.add_cog(Moderation(bot))
