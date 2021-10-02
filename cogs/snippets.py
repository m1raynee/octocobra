"""Credits: https://github.com/python-discord/bot/blob/main/bot/exts/info/code_snippets.py"""

import re
import textwrap
from contextlib import suppress
from typing import Callable, List, Tuple, Union
from urllib.parse import quote_plus

from disnake.ext import commands
import disnake
from aiohttp import ClientResponseError

from .utils.helpers import wait_for_deletion

GITHUB_RE = re.compile(
    r'https://github\.com/(?P<repo>[a-zA-Z0-9-]+/[\w.-]+)/blob/'
    r'(?P<path>[^#>]+)(\?[^#>]+)?(#L(?P<start_line>\d+)(([-~:]|(\.\.))L(?P<end_line>\d+))?)'
)

GITHUB_GIST_RE = re.compile(
    r'https://gist\.github\.com/([a-zA-Z0-9-]+)/(?P<gist_id>[a-zA-Z0-9]+)/*'
    r'(?P<revision>[a-zA-Z0-9]*)/*#file-(?P<file_path>[^#>]+?)(\?[^#>]+)?'
    r'(-L(?P<start_line>\d+)([-~:]L(?P<end_line>\d+))?)'
)

GITHUB_HEADERS = {'Accept': 'application/vnd.github.v3.raw'}


class Snippets(commands.Cog):
    """Code snipets from Github (Gists)."""

    def __init__(self, bot):
        self.bot = bot

        self.patterns: List[Tuple[re.Pattern, Callable]] = [
            (GITHUB_RE, self.fetch_github),
            (GITHUB_GIST_RE, self.fetch_github_gist)
        ]

    def _snippet_to_codeblock(self, file_contents: str, file_path: str, start_line: str, end_line: str) -> str:
        """
        Given the entire file contents and target lines, creates a code block.
        First, we split the file contents into a list of lines and then keep and join only the required
        ones together.
        We then dedent the lines to look nice, and replace all ` characters with `\u200b to prevent
        markdown injection.
        Finally, we surround the code with ``` characters.
        """
        # Parse start_line and end_line into integers
        if end_line is None:
            start_line = end_line = int(start_line)
        else:
            start_line = int(start_line)
            end_line = int(end_line)

        split_file_contents = file_contents.splitlines()

        # Make sure that the specified lines are in range
        if start_line > end_line:
            start_line, end_line = end_line, start_line
        if start_line > len(split_file_contents) or end_line < 1:
            return ''
        start_line = max(1, start_line)
        end_line = min(len(split_file_contents), end_line)

        # Gets the code lines, dedents them, and inserts zero-width spaces to prevent Markdown injection
        required = '\n'.join(split_file_contents[start_line - 1:end_line])
        required = textwrap.dedent(required).rstrip().replace('`', '`\u200b')

        # Extracts the code language and checks whether it's a "valid" language
        language = file_path.split('/')[-1].split('.')[-1]
        is_valid_language = language.replace('-', '').replace('+', '').replace('_', '').isalnum()
        if not is_valid_language:
            language = ''

        # Adds a label showing the file path to the snippet
        if start_line == end_line:
            ret = f'`{file_path}` line {start_line}\n'
        else:
            ret = f'`{file_path}` lines {start_line} to {end_line}\n'

        if len(required) != 0:
            return f'{ret}```{language}\n{required}```'
        # Returns an empty codeblock if the snippet is empty
        return f'{ret}``` ```'

    def _find_ref(self, path: str, refs: tuple) -> tuple:
        """Loops through all branches and tags to find the required ref."""
        # Base case: there is no slash in the branch name
        ref, file_path = path.split('/', 1)
        # In case there are slashes in the branch name, we loop through all branches and tags
        for possible_ref in refs:
            if path.startswith(possible_ref['name'] + '/'):
                ref = possible_ref['name']
                file_path = path[len(ref) + 1:]
                break
        return ref, file_path

    async def _fetch_response(self, url: str, response_format: str, **kwargs) -> Union[str, dict]:
        """Makes http requests using aiohttp."""
        async with self.bot.http_session.get(url, raise_for_status=True, **kwargs) as response:
            if response_format == 'text':
                return await response.text()
            elif response_format == 'json':
                return await response.json()

    async def fetch_github(
        self,
        repo: str,
        path: str,
        start_line: str,
        end_line: str
    ) -> str:
        branches = await self._fetch_response(
            f'https://api.github.com/repos/{repo}/branches',
            'json',
            headers=GITHUB_HEADERS
        )
        tags = await self._fetch_response(f'https://api.github.com/repos/{repo}/tags', 'json', headers=GITHUB_HEADERS)
        refs = branches + tags
        ref, file_path = self._find_ref(path, refs)

        file_contents = await self._fetch_response(
            f'https://api.github.com/repos/{repo}/contents/{file_path}?ref={ref}',
            'text',
            headers=GITHUB_HEADERS,
        )
        return self._snippet_to_codeblock(file_contents, file_path, start_line, end_line)

    async def fetch_github_gist(
        self,
        gist_id: str,
        revision: str,
        file_path: str,
        start_line: str,
        end_line: str
    ) -> str:
        """Fetches a snippet from a GitHub gist."""
        gist_json = await self._fetch_response(
            f'https://api.github.com/gists/{gist_id}{f"/{revision}" if len(revision) > 0 else ""}',
            'json',
            headers=GITHUB_HEADERS,
        )

        # Check each file in the gist for the specified file
        for gist_file in gist_json['files']:
            if file_path == gist_file.lower().replace('.', '-'):
                file_contents = await self._fetch_response(
                    gist_json['files'][gist_file]['raw_url'],
                    'text',
                )
                return self._snippet_to_codeblock(file_contents, gist_file, start_line, end_line)
        return ''

    async def parse_snippets(self, content: str):
        all_snipets = []

        for pattern, handler in self.patterns:
            for match in pattern.finditer(content):
                with suppress(ClientResponseError):
                    snippet = await handler(**match.groupdict())
                all_snipets.append(snippet)

        return '\n'.join(sorted(all_snipets))

    @commands.Cog.listener()
    async def on_message(self, message: disnake.Message):
        snipets = await self.parse_snippets(message.content)
        destination = message.channel

        if 0 < len(snipets) <= 2000 and snipets.count('\n') <= 15:
            with suppress(disnake.NotFound):
                await message.edit(suppress=True)
            kwargs = {'content': snipets}

            if len(snipets) > 1000 and message.channel.id not in (808035299094691882,889872309639315497):
                destination = self.bot.get_channel(808035299094691882)
            
                await message.reply(
                    'The snippet you tried to send was too long. '
                    f'Please see {destination.mention} for the full snippet.'
                )
            else:
                kwargs['reference'] = message
            await wait_for_deletion(
                message.author.id,
                {'content': snipets, },
                destination
            )

def setup(bot):
    bot.add_cog(Snippets(bot))
