import asyncio
import datetime
import textwrap

from disnake.ext import commands
import disnake

from cogs.utils.converters import FutureTime, futuretime_autocomp

from .utils.db.remind import Reminders
from .utils.views import Confirm


class Timer:
    __slots__ = ('args', 'kwargs', 'event', 'id', 'created_at', 'expires')

    def __init__(self, *, record: Reminders):
        self.id = record.id

        extra = record.extra
        self.args = extra.get('args', [])
        self.kwargs = extra.get('kwargs', {})
        self.event = record.event
        self.created_at = record.created
        self.expires = record.expires
        self.author_id = record.author_id

    @classmethod
    def temporary(cls, *, expires, created, event, author_id, args, kwargs):
        pseudo = {
            'extra': {'args': args, 'kwargs': kwargs},
            'event': event,
            'created': created,
            'expires': expires,
            'author_id': author_id
        }
        return cls(record=Reminders(**pseudo))

    def __eq__(self, other):
        try:
            return self.id == other.id
        except AttributeError:
            return False

    def __hash__(self):
        return hash(self.id)

    @property
    def expires_delta(self):
        return disnake.utils.format_dt(self.expires, 'R')
    @property
    def created_delta(self):
        return disnake.utils.format_dt(self.created_at, 'R')

    def __repr__(self):
        return f'<Timer created={self.created_at} expires={self.expires} event={self.event}>'

class Reminder(commands.Cog):
    """Reminders to do something."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._have_data = asyncio.Event(loop=bot.loop)
        self._current_timer = None
        self._task = bot.loop.create_task(self.dispatch_timers())

    def cog_unload(self):
        self._task.cancel()

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(error)
        if isinstance(error, commands.TooManyArguments):
            await ctx.send(f'You called the {ctx.command.name} command with too many arguments.')

    async def get_active_timer(self, *, days=7):
        record = await (Reminders
            .filter(expires__gt=disnake.utils.utcnow() + datetime.timedelta(days=days))
            .order_by('expires')
            .first()
        )

        return Timer(record=record) if record else None

    async def wait_for_active_timers(self, *, days=7):
        timer = await self.get_active_timer(days=days)
        if timer is not None:
            self._have_data.set()
            return timer

        self._have_data.clear()
        self._current_timer = None
        await self._have_data.wait()
        return await self.get_active_timer(days=days)

    async def call_timer(self, timer: Timer):
        # delete the timer
        await Reminders.filter(id=timer.id).delete()

        # dispatch the event
        event_name = f'{timer.event}_timer_complete'
        self.bot.dispatch(event_name, timer)

    async def dispatch_timers(self):
        try:
            while not self.bot.is_closed():
                # can only asyncio.sleep for up to ~48 days reliably
                # so we're gonna cap it off at 40 days
                # see: http://bugs.python.org/issue20493
                timer = self._current_timer = await self.wait_for_active_timers(days=40)
                now = disnake.utils.utcnow()

                if timer.expires >= now:
                    to_sleep = (timer.expires - now).total_seconds()
                    await asyncio.sleep(to_sleep)

                await self.call_timer(timer)
        except asyncio.CancelledError:
            raise
        except (OSError, disnake.ConnectionClosed):
            self._task.cancel()
            self._task = self.bot.loop.create_task(self.dispatch_timers())

    async def short_timer_optimisation(self, seconds, timer):
        await asyncio.sleep(seconds)
        event_name = f'{timer.event}_timer_complete'
        self.bot.dispatch(event_name, timer)

    async def create_timer(self, when: datetime.datetime, event: str, author_id: int, *args, **kwargs) -> Timer:
        """
        Creates a timer.
        
        Parameters
        ----------
        when: datetime.datetime
            When the timer should fire.
        event: str
            The name of the event to trigger.
            Will transform to 'on_{event}_timer_complete'.
        \*args
            Arguments to pass to the event
        \*\*kwargs
            Keyword arguments to pass to the event
        created: datetime.datetime
            Special keyword-only argument to use as the creation time.
            Should make the timedeltas a bit more consistent.

        Note
        ------
        Arguments and keyword arguments must be JSON serialisable.

        Returns
        --------
        :class:`Timer`
        """

        try:
            now = kwargs.pop('created')
        except KeyError:
            now = disnake.utils.utcnow()

        # Remove timezone information since the database does not deal with it
        when = when.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        now = now.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        timer = Timer.temporary(
            event=event,
            args=args,
            kwargs=kwargs,
            expires=when,
            created=now,
            author_id=author_id
        )
        delta = (when - now).total_seconds()
        if delta <= 60:
            # a shortcut for small timers
            self.bot.loop.create_task(self.short_timer_optimisation(delta, timer))
            return timer

        row = await (Reminders
            .create(
                event=event,
                extra={'args': args, 'kwargs': kwargs},
                expires=when,
                created=now,
                author_id=author_id
            )
        )

        timer.id = row.id

        # only set the data check if it can be waited on
        if delta <= (86400 * 40): # 40 days
            self._have_data.set()

        # check if this timer is earlier than our currently run timer
        if self._current_timer and when < self._current_timer.expires:
            # cancel the task and re-run it
            self._task.cancel()
            self._task = self.bot.loop.create_task(self.dispatch_timers())

        return timer

    @commands.slash_command()
    async def reminder(*_):
        pass
    
    @reminder.sub_command(name='create')
    async def reminder_create(self, inter: disnake.ApplicationCommandInteraction,
        when: str = commands.Param(converter=FutureTime, autocomplete=futuretime_autocomp),
        reason: str = '\u2026'
    ):
        """
        Reminds you of something after a certain amount of time.
        Parameters
        ----------
        time: Any direct date (e.g. YYYY-MM-DD) or a human readable offset.
        reason: Something to remind you of
        """


        await inter.response.send_message(f"Alright {inter.author.mention}, {disnake.utils.format_dt(when.dt, 'R')}: {reason}")
        msg = await inter.original_message()
        await self.create_timer(
            when.dt, 'reminder', inter.author.id,
            inter.channel.id, reason,
            created=inter.created_at,
            message_id=msg.id
        )

    @reminder.sub_command(name='list')
    async def reminder_list(self, inter: disnake.ApplicationCommandInteraction):
        """Shows the 10 latest currently running reminders."""

        records = await (Reminders
            .filter(event = 'reminder', author_id = inter.author.id)
            .only('id', 'expires', 'extra')
            .limit(10)
        )

        if len(records) == 0:
            return await inter.response.send_message('No currently running reminders.', ephemeral=True)

        e = disnake.Embed(colour=0x0084c7, title='Reminders')

        if len(records) == 10:
            e.set_footer(text='Only showing up to 10 reminders.')
        else:
            e.set_footer(text=f'{len(records)} reminder{"s" if len(records) > 1 else ""}')

        for _id, expires, message in records:
            shorten = textwrap.shorten(message, width=512)
            e.add_field(name=f'{_id}: {disnake.utils.format_dt(expires, "R")}', value=shorten, inline=False)

        await inter.response.send_message(embed=e, ephemeral=True)

    @reminder.sub_command(name='delete')
    async def reminder_delete(self, inter: disnake.ApplicationCommandInteraction, id: int):
        """
        Deletes a reminder by its ID (use reminder list command).
        Parameters
        ----------
        id: Reminder's ID
        """

        query = await (Reminders
            .filter(id=id, event='reminder', author_id=inter.author.id)
            .delete()
        )

        if query == 0:
            return await inter.response.send_message('Could not delete any reminders with that ID.', ephemeral=True)

        # if the current timer is being deleted
        if self._current_timer and self._current_timer.id == id:
            # cancel the task and re-run it
            self._task.cancel()
            self._task = self.bot.loop.create_task(self.dispatch_timers())

        await inter.response.send_message('Successfully deleted reminder.', ephemeral=True)

    @reminder.sub_command(name='clear')
    async def reminder_clear(self, inter: disnake.ApplicationCommandInteraction):
        """Clears all reminders you have set."""

        # For UX purposes this has to be two queries.

        total = await (Reminders
            .filter(event='reminder', author_id=inter.author.id)
            .count()
        )

        if total == 0:
            return await inter.response.send_message('You don\'t have any reminders to delete.', ephemeral=True)
        async def callback(value, interaction):
            if not value:
                return await interaction.response.send_message('Aborting')
            await (Reminders
                .filter(event='reminder', author_id=inter.author.id)
                .delete()
            )
            if self._current_timer and self._current_timer.author_id == inter.author.id:
                self._task.cancel()
                self._task = self.bot.loop.create_task(self.dispatch_timers())

            await interaction.response.edit_message(f'Successfully deleted {total} reminder{"s" if total > 1 else ""}.')

        view = Confirm(callback, listen_to=(inter.author.id,))
        await inter.response.send_message(f'Are you sure you want to delete {total} reminder{"s" if total > 1 else ""}?', view=view)

    @commands.Cog.listener()
    async def on_reminder_timer_complete(self, timer: Timer):
        channel_id, message = timer.args
        author_id = timer.author_id

        try:
            channel = self.bot.get_channel(channel_id) or (await self.bot.fetch_channel(channel_id))
        except disnake.HTTPException:
            return

        guild_id = channel.guild.id if isinstance(channel, (disnake.TextChannel, disnake.Thread)) else '@me'
        message_id = timer.kwargs.get('message_id')
        msg = f'<@{author_id}>, {timer.created_at}: {message}'
        view = disnake.utils.MISSING

        if message_id:
            url = f'https://discord.com/channels/{guild_id}/{channel.id}/{message_id}'
            view = disnake.ui.View()
            view.add_item(disnake.ui.Button(label='Go to original message', url=url))

        try:
            await channel.send(msg, view=view)
        except disnake.HTTPException:
            return

def setup(bot):
    bot.add_cog(Reminder(bot))
