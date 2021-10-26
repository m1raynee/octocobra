from __future__ import annotations
import re
from operator import attrgetter

import dateparser
import disnake
from disnake.ext import commands

id_pattern = re.compile(r'[0-9]{15,19}')

def clean_inter_content(
    *,
    fix_channel_mentions: bool = False,
    use_nicknames: bool = True,
    escape_markdown: bool = False,
    remove_markdown: bool = False,
):
    async def convert(inter: disnake.ApplicationCommandInteraction, argument: str):
        if inter.guild:
            def resolve_member(id: int) -> str:
                m = inter.guild.get_member(id)
                return f'@{m.display_name if use_nicknames else m.name}' if m else '@deleted-user'

            def resolve_role(id: int) -> str:
                r = inter.guild.get_role(id)
                return f'@{r.name}' if r else '@deleted-role'
        else:
            def resolve_member(id: int) -> str:
                m = inter.bot.get_user(id)
                return f'@{m.name}' if m else '@deleted-user'

            def resolve_role(id: int) -> str:
                return '@deleted-role'

        if fix_channel_mentions and inter.guild:
            def resolve_channel(id: int) -> str:
                c = inter.guild.get_channel(id)
                return f'#{c.name}' if c else '#deleted-channel'
        else:
            def resolve_channel(id: int) -> str:
                return f'<#{id}>'

        transforms = {
            '@': resolve_member,
            '@!': resolve_member,
            '#': resolve_channel,
            '@&': resolve_role,
        }

        def repl(match: re.Match) -> str:
            type = match[1]
            id = int(match[2])
            transformed = transforms[type](id)
            return transformed

        result = re.sub(r'<(@[!&]?|#)([0-9]{15,20})>', repl, argument)
        if escape_markdown:
            result = disnake.utils.escape_markdown(result)
        elif remove_markdown:
            result = disnake.utils.remove_markdown(result)

        # Completely ensure no mentions escape:
        return disnake.utils.escape_mentions(result)

    return convert

async def tag_name(inter: disnake.ApplicationCommandInteraction, argument: str):
    converted = await clean_inter_content()(inter, argument)
    lower = converted.lower().strip()

    if not lower:
        raise commands.BadArgument('Missing tag name')

    if len(lower) > 50:
        raise commands.BadArgument('Tag name must be less than 50')

    return lower

class _checker:
    def check(self, obj: object, attrs):
        name = obj.__class__.__name__

        _all = all
        attrget = attrgetter

        # Special case the single element call
        if len(attrs) == 1:
            k, v = attrs.popitem()
            pred = attrget(k.replace('__', '.'))
            if pred(obj) == v:
                return obj
            raise disnake.NotFound(f"{name} doesn't match the conditions.")

        converted = [(attrget(attr.replace('__', '.')), value) for attr, value in self.attrs.items()]

        if _all(pred(obj) == value for pred, value in converted):
            return obj
        raise disnake.NotFound(f"{name} doesn't match the conditions.")

class UserCondition(_checker):
    def __init__(self, **attrs) -> None:
        super().__init__()
        self.attrs = attrs
        self.inter = None
        self.id = None
    
    def __call__(self, inter: disnake.ApplicationCommandInteraction, argument: str) -> None:
        self.inter = inter
        if not argument.isdigit():
            raise TypeError('This field must be a integer')
        match = re.match(id_pattern, argument)
        if match is None:
            raise ValueError(f'{argument!r} is not an id')
        self.id = int(match.group())
        return self.convert()
    
    async def convert(self):
        user = await self.inter.bot.fetch_user(self.id)
        return self.check(user, self.attrs)
# usage: arg: str = commands.param(converter=User(bot=True))

class Time:
    settings={'PREFER_DATES_FROM': 'future', 'RETURN_AS_TIMEZONE_AWARE': True}
    def __init__(self, inter: disnake.ApplicationCommandInteraction, argument: str):
        now = inter.created_at
        self.argument = argument
    
        dt = dateparser.parse(argument, settings=self.settings)

        if dt is None:
            raise commands.BadArgument('Invalid time provided, try e.g. "tomorrow" or "3 days"')

        for field in ('hour', 'minute', 'second', 'microsecond'):
            if getattr(dt, field) is None:
                setattr(dt, field, getattr(now, field))

        self.dt = dt
        self._past = dt < now
# usage: arg: str = commands.param(converter=Time)

class FutureTime(Time):
    def __init__(self, inter: disnake.ApplicationCommandInteraction, argument: str):
        super().__init__(inter, argument)

        if self._past:
            raise commands.BadArgument('This time is in the past')
# usage: arg: str = commands.param(converter=FutureTime)

async def futuretime_autocomp(inter, value):
    try:
        converted = FutureTime(inter, value)
    except commands.BadArgument as exc:
        return {str(exc): value}
    return {converted.dt.strftime('on %a, %d %b %Y, at %H:%M:%S in UTC'): value}

class ActionReason:
    def __init__(self, inter: disnake.ApplicationCommandInteraction, argument: str):
        if argument is None:
            self.ret = f'Action done by {inter.author} (ID: {inter.author.id})'
            return
        ret = f'{inter.author} (ID: {inter.author.id}): {argument}'

        if len(ret) > 512:
            reason_max = 512 - len(ret) + len(argument)
            raise commands.BadArgument(f'Reason is too long ({len(argument)}/{reason_max})')
        self.ret = ret

async def action_autocomp(inter: disnake.ApplicationCommandInteraction, value: str):
    try:
        converted = ActionReason(inter, value)
    except commands.BadArgument as exc:
        return {str(exc): value}
    return {converted.ret: value}