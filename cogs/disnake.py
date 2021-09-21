import io
import re
import os
import zlib

from disnake.ext import commands
import disnake

from .utils import fuzzy
from bot import DisnakeHelper

DOC_KEYS = {
    'latest': 'https://disnake.readthedocs.io/en/latest/',
    'python': 'https://docs.python.org/3',
    'dislash': 'https://dislashpy.readthedocs.io/en/latest/',
    'dpy-master': 'http://discordpy.readthedocs.io/en/master/'
}

class SphinxObjectFileReader:
    # Inspired by Sphinx's InventoryFileReader
    BUFSIZE = 16 * 1024

    def __init__(self, buffer):
        self.stream = io.BytesIO(buffer)

    def readline(self):
        return self.stream.readline().decode('utf-8')

    def skipline(self):
        self.stream.readline()

    def read_compressed_chunks(self):
        decompressor = zlib.decompressobj()
        while True:
            chunk = self.stream.read(self.BUFSIZE)
            if len(chunk) == 0:
                break
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def read_compressed_lines(self):
        buf = b''
        for chunk in self.read_compressed_chunks():
            buf += chunk
            pos = buf.find(b'\n')
            while pos != -1:
                yield buf[:pos].decode('utf-8')
                buf = buf[pos + 1:]
                pos = buf.find(b'\n')

class Disnake(commands.Cog, name='disnake'):
    """Docs and other disnake's guild things."""

    def __init__(self, bot: DisnakeHelper):
        self.bot = bot

    async def cog_slash_command_error(self, inter: disnake.ApplicationCommandInteraction, error: Exception) -> None:
        if isinstance(error, RuntimeError):
            if inter.response.is_done():
                m = inter.followup.send
            else:
                m = inter.response.send_message
            return await m(error, ephemeral=True)

        return await super().cog_slash_command_error(inter, error)

    def parse_object_inv(self, stream: SphinxObjectFileReader, url: str):
        # key: URL
        # n.b.: key doesn't have `discord` or `discord.ext.commands` namespaces
        result = {}

        # first line is version info
        inv_version = stream.readline().rstrip()

        if inv_version != '# Sphinx inventory version 2':
            raise RuntimeError('Invalid objects.inv file version.')

        # next line is "# Project: <name>"
        # then after that is "# Version: <version>"
        projname = stream.readline().rstrip()[11:]
        version = stream.readline().rstrip()[11:]

        # next line says if it's a zlib header
        line = stream.readline()
        if 'zlib' not in line:
            raise RuntimeError('Invalid objects.inv file, not z-lib compatible.')

        # This code mostly comes from the Sphinx repository.
        entry_regex = re.compile(r'(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)')
        for line in stream.read_compressed_lines():
            match = entry_regex.match(line.rstrip())
            if not match:
                continue

            name, directive, prio, location, dispname = match.groups()
            domain, _, subdirective = directive.partition(':')
            if directive == 'py:module' and name in result:
                # From the Sphinx Repository:
                # due to a bug in 1.1 and below,
                # two inventory entries are created
                # for Python modules, and the first
                # one is correct
                continue

            # Most documentation pages have a label
            if directive == 'std:doc':
                subdirective = 'label'

            if location.endswith('$'):
                location = location[:-1] + name

            key = name if dispname == '-' else dispname
            prefix = f'{subdirective}:' if domain == 'std' else ''

            if projname == 'disnake':
                key = key.replace('disnake.ext.commands.', '').replace('disnake.', '')

            result[f'{prefix}{key}'] = os.path.join(url, location)

        return result

    async def prepare_cache(self):
        cache = {}
        for key, page in DOC_KEYS.items():
            cache[key] = {}
            async with self.bot.session.get(page + '/objects.inv') as resp:
                if resp.status != 200:
                    raise RuntimeError('Cannot build rtfm lookup table, try again later.')

                stream = SphinxObjectFileReader(await resp.read())
                cache[key] = self.parse_object_inv(stream, page)

        self._cache = cache
    
    async def do_rtfm(self, inter: disnake.ApplicationCommandInteraction, key: str, obj):
        if not hasattr(self, '_cache'):
            await self.prepare_cache()

        if obj is None:
            await inter.response.send_message(DOC_KEYS[key])
            return

        obj = re.sub(r'^(?:disnake\.(?:ext\.)?)?(?:commands\.)?(.+)', r'\1', obj)

        if key.startswith(('latest', 'dpy-master')):
            # point the abc.Messageable types properly:
            q = obj.lower()
            for name in dir(disnake.abc.Messageable):
                if name[0] == '_':
                    continue
                if q == name:
                    obj = f'abc.Messageable.{name}'
                    break

        cache = list(self._cache[key].items())

        matches = fuzzy.finder(obj, cache, key=lambda t: t[0], lazy=False)[:8]

        if len(matches) == 0:
            return await inter.response.send_message('Could not find anything. Sorry.')

        e = disnake.Embed(
            description = '\n'.join(f'[`{key}`]({url})' for key, url in matches),
            colour=0x0084c7
        )
        await inter.response.send_message(embed=e)

        # if ctx.guild and ctx.guild.id in self.bot._test_guilds:
        #     query = 'INSERT INTO rtfm (user_id) VALUES ($1) ON CONFLICT (user_id) DO UPDATE SET count = rtfm.count + 1;'
        #     await ctx.db.execute(query, ctx.author.id)

    @commands.slash_command(
        description='Gives you a documentation link for a selected doc entity.',
        options=[
            disnake.Option('object', 'Requested object', disnake.OptionType.string, True),
            disnake.Option(
                'docs', 'Documentation key',
                choices=[
                    disnake.OptionChoice('disnake latest', 'latest'),
                    disnake.OptionChoice('Python 3.x', 'python'),
                    disnake.OptionChoice('dislash.py', 'dislash'),
                    disnake.OptionChoice('discord.py master', 'dpy-master'),
                ]
            ),
        ]
    )
    async def rtfm(self, inter, object, language = None):
        language = language or 'latest'
        await self.do_rtfm(inter, language, object)
    

def setup(bot):
    bot.add_cog(Disnake(bot))
