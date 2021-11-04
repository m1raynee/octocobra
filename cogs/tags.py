import asyncio
import datetime
from os import name
from typing import Optional, Union, List
from functools import partial
from textwrap import shorten

from disnake.ext import commands
from disnake import ui
import disnake
from tortoise.exceptions import IntegrityError

from .utils.db import in_transaction, TransactionWrapper, F
from .utils.db.tags import TagTable, TagLookup
from .utils.send import safe_send_prepare
from .utils.converters import tag_name, clean_content
from .utils import paginator
from .utils.views import Confirm

TAG_PREFIXES = {
    '\N{NOTEBOOK WITH DECORATIVE COVER}': ('Modules and packages', 'Links to important libraries and extantions'),
    '\N{SCROLL}': ('Code snippets', 'Helpful, illustrative code examples'),
    '\N{MEMO}': ('Tips and tricks', 'Short but helpful tips for each other'),
    '\N{FACE WITH TEARS OF JOY}': ('Memes', 'Funny things'),
    '\N{BOOKMARK}': ('No category', 'No prefix provided'),
}
class TagPrefixSelect(ui.Select['PrefixView']):
    def __init__(self):
        super().__init__(
            placeholder='Select the appropriate prefix',
            options=[
                disnake.SelectOption(label=v[0], description=v[1], emoji=k, value=k)
                for k, v in TAG_PREFIXES.items()
            ]
        )
    
    async def callback(self, interaction: disnake.MessageInteraction):
        await interaction.response.edit_message(content='You can dismiss this message.', view=None)
        self.view.selected = self.values[0]
        self.view.stop()

class PrefixView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(TagPrefixSelect())
    
    async def start(self):
        if not await self.wait():
            return self.selected
        return '\N{BOOKMARK}'

class TagCreateView(disnake.ui.View):
    message: disnake.Message

    def __init__(
        self,
        init_interaction: disnake.Interaction,
        cog: 'Tags',
        edit: Optional[TagTable] = None
    ):
        super().__init__(timeout=300)
        self.bot = cog.bot
        self._init_interaction = init_interaction
        self._cog = cog
        self._edit = edit

        self.message = None
        self.is_aborted = False

        if edit is not None:
            self.remove_item(self.name_button)
            self.name = edit.name
            self.content = edit.content
            self.prefix = edit.prefix
        else:
            self.name = self.content = None
            self.prefix = '\N{bookmark}'

    def response_check(self, msg):
        return self._init_interaction.channel == msg.channel and msg.author == self._init_interaction.author

    def prepare_embed(self):
        e = disnake.Embed(title='Tag creation', color=0x0084c7)
        e.add_field(name='Name', value=self.name, inline=False)
        e.add_field(name='Content', value=shorten(str(self.content), 1024), inline=False)
        e.add_field(name='Prefix', value=f'\\{self.prefix} {TAG_PREFIXES[self.prefix][0]}', inline=False)

        if len(str(self.content)) > 1024:
            e.description = '\n**Hint:** Tag content reached embed field limitation, this will not affect the content'
        return e

    def lock_all(self):
        for child in self.children:
            if child.label == 'Abort':
                continue
            child.disabled = True

    def unlock_all(self):
        for child in self.children:
            if child.label == 'Confirm':
                if self._edit:
                    if self._edit.content != self.content or self._edit.prefix != self.prefix:
                        child.disabled = False
                        continue
                elif self.name is not None and self.content is not None:
                    child.disabled = False
                else:
                    child.disabled = True
            else:
                child.disabled = False

    async def interaction_check(self, interaction: disnake.Interaction) -> bool:
        if interaction.author == self._init_interaction.author:
            return True
        await interaction.response.send_message('You\'re not an author of this View.', ephemeral=True)
        return False

    @ui.button(
        label='Name',
        style=disnake.ButtonStyle.secondary
    )
    async def name_button(self, button: disnake.Button, interaction: disnake.MessageInteraction):
        self.lock_all()
        msg_content = 'Cool, let\'s make a name. Send the tag name in the next message...'

        await interaction.response.edit_message(content=msg_content, view=self)
        msg = await self.bot.wait_for('message', check=self.response_check, timeout=60)
        if self.is_finished():
            return

        content = None
        try:
            name = await tag_name(interaction, msg.content)
        except commands.BadArgument as e:
            content = f'{e}. Press "Name" to retry.'
        else:
            if self._cog.is_tag_being_made(name):
                content = 'Sorry. This tag is currently being made by someone.'
            else:
                rows = await (TagLookup
                    .filter(name=name)
                    .limit(1)
                )
                if not rows:
                    self.name = name
                    self._cog.add_in_progress_tag(name)
                    self.remove_item(button)
                else:
                    content = 'Sorry. A tag with that name already exists.'

        self.unlock_all()
        await self.message.edit(content=content, embed=self.prepare_embed(), view=self)
    
    @ui.button(
        label='Content',
        style=disnake.ButtonStyle.secondary
    )
    async def content_button(self, button: disnake.Button, interaction: disnake.MessageInteraction):
        self.lock_all()
        msg_content = f'Cool, let\'s {"edit the" if self._edit else "make a"} content. Send the tag content in the next message...'

        await interaction.response.edit_message(content=msg_content, view=self)
        msg = await self.bot.wait_for('message', check=self.response_check, timeout=300)
        if self.is_finished():
            return

        if msg.content:
            content = clean_content()(interaction, msg.content)
        else:
            content = msg.content

        if msg.attachments:
            content += f'\n{msg.attachments[0].url}'

        c = None
        if len(content) > 2000:
            c = 'Tag content is a maximum of 2000 characters.'
        else:
            self.content = content

        self.unlock_all()
        await self.message.edit(content=c, embed=self.prepare_embed(), view=self)
    
    @ui.button(
        label='Prefix',
        style=disnake.ButtonStyle.secondary
    )
    async def prefix_button(self, button: disnake.Button, interaction: disnake.MessageInteraction):
        view = PrefixView()
        await interaction.response.send_message('Please choose one of prefixes', view=view, ephemeral=True)
        self.prefix = await view.start()
        if self.is_finished():
            return

        self.unlock_all()
        await self.message.edit(embed=self.prepare_embed())

    @ui.button(
        label='Confirm',
        style=disnake.ButtonStyle.success,
        disabled=True
    )
    async def comfirm_button(self, button: disnake.Button, interaction: disnake.MessageInteraction):
        if self._edit and self._edit.content == self.content:
            return await interaction.response.edit_message(
                content='Content still the same...\nHint: edit it by pressing "Content"'
            )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        self.last_interaction = interaction
        self._cog.remove_in_progress_tag(self.name)
        self.stop()
    
    @ui.button(
        label='Abort',
        style=disnake.ButtonStyle.danger
    )
    async def abort_button(self, button: disnake.Button, interaction: disnake.MessageInteraction):
        self._cog.remove_in_progress_tag(name)
        await interaction.response.edit_message(
            content=f'Tag {"edi" if self._edit else "crea"}tion aborted.', # cspell: ignoreline
            view=None, embed=None
        )
        self.stop()

    async def on_error(self, error: Exception, item, interaction: disnake.MessageInteraction) -> None:
        if isinstance(error, asyncio.TimeoutError):
            if interaction.response.is_done():
                method = self.message.edit
            else:
                method = interaction.response.edit_message
            if self.name is not None:
                self._cog.remove_in_progress_tag(self.name)
            await method(content='You took too long. Goodbye.', view=None, embed=None)
            return self.stop()
        raise error

class TagSource(paginator.BaseListSource):
    entries: List[TagLookup]
    def __init__(self, entries: List[TagLookup]):
        super().__init__(entries, per_page=20)

    async def format_page(self, view: paginator.PaginatorView, page: List[TagLookup]):
        e = self.base_embed(view, page)
        e.description = '\n'.join([
            f'{i}. {row.name} (id: {row.id})'
            for i, row
            in enumerate(page, view.current_page*self.per_page+1)
        ])
        return e

name_converter = clean_content()
async def name_autocomp(inter: disnake.ApplicationCommandInteraction, user_input: str):
    user_input = name_converter(inter, user_input)
    rows = await (TagLookup
        .filter(name__contains=user_input)
        .order_by('name')
        .limit(20)
        .only('name', 'original_id')
        .prefetch_related('original')
    )
    return {
        f'{row.original.prefix} {row.name}': row.name
        for row in rows
    }

name_param = partial(commands.param, converter=name_converter, autocomp=name_autocomp)

class Tags(commands.Cog):
    """Commands to fetch something by a tag name"""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self._tags_being_made = set()

    async def get_tag(self, name: str, original=True, only=('id', 'name', 'content')) -> Union[TagTable, TagLookup]:
        def not_found(rows):
            if rows is None or len(rows) == 0:
                raise RuntimeError('Tag not found.')

            names = '\n'.join(r.name for r in rows)
            raise RuntimeError(f'Tag not found. Did you mean...\n{names}')

        tag = await (TagTable
            .filter(name=name)
            .only(*only)
            .first()
        )
        if tag is None:
            tag = await (TagLookup
                .filter(name=name)
                .first()
                .prefetch_related('original')
            )
            if original and tag is not None:
                tag = tag.original
        if tag is None:
            query = await (TagLookup
                .filter(name__contains=name)
                .limit(3)
                .only('name')
            )
            not_found(query)

        return tag

    async def create_tag(self, inter: disnake.Interaction, name, content, prefix):
        async with in_transaction() as tr:
            tr: TransactionWrapper
            try:
                tag = await TagTable.create(
                    name = name,
                    content = content,
                    owner_id = inter.author.id,
                    prefix=prefix
                )
                await TagLookup.create(
                    name = name,
                    original = tag,
                    owner_id = inter.author.id,
                )
            except IntegrityError:
                await tr.rollback()
                await inter.followup.send('This tag already exists.')
            except:
                await tr.rollback()
                await inter.followup.send('Could not create tag.')
                raise
            else:
                await tr.commit()
                await inter.followup.send(f'Tag {name} successfully created.')

    def is_tag_being_made(self, name: str):
        return name.lower() in self._tags_being_made
    def add_in_progress_tag(self, name: str):
        self._tags_being_made.add(name.lower())
    def remove_in_progress_tag(self, name: str):
        self._tags_being_made.discard(name.lower())

    def can_menage(self, user, tag: TagTable):
        if not (user and (tag.owner_id == user.id or self.bot.owner.id == user.id)):
            raise commands.CheckFailure('You cannot menage this tag.')

    @commands.slash_command()
    async def tag(*_):
        pass

    @tag.sub_command(name='show')
    async def tag_show(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: str = name_param(),
        type = commands.param(
            'rich',
            choices = [
                disnake.OptionChoice('Rich', 'rich'),
                disnake.OptionChoice('Raw', 'raw')
            ]
        )
    ):
        """
        Search for a tag.
        Parameters
        ----------
        name: Requested tag name
        type: Whether what content type will be shown
        """
        try:
            tag = await self.get_tag(name)
        except RuntimeError as e:
            return await inter.response.send_message(e, ephemeral=True)
        
        if type == 'raw':
            first_step = disnake.utils.escape_markdown(tag.content)
            kwargs = await safe_send_prepare(first_step.replace('<', '\\<'), escape_mentions=False)
        else:
            kwargs = dict(content=tag.content)

        await inter.response.send_message(**kwargs)
        await (TagTable
            .filter(id=tag.id)
            .update(uses = F('uses') + 1)
        )

    @tag.sub_command(name='create')
    async def tag_create(self, inter: disnake.ApplicationCommandInteraction):
        """Creates a new tag owned by you."""
        view = TagCreateView(inter, self)
        await inter.response.send_message(embed=view.prepare_embed(), view=view)
        view.message = await inter.original_message()

        if await view.wait():
            if view.name is not None:
                self.remove_in_progress_tag(view.name)
            return await view.message.edit(content='You took too long. Goodbye.', view=None, embed=None)
        else:
            await view.message.edit(view=None)

        if hasattr(view, 'last_interaction'):
            await self.create_tag(view.last_interaction, view.name, view.content, view.prefix)

    @tag.sub_command(name='alias')
    async def tag_alias(
        self,
        inter: disnake.ApplicationCommandInteraction,
        new_name: str = commands.param(converter=name_converter),
        old_name: str = name_param()
    ):
        """
        Creates an alias for a pre-existing tag.
        Parameters
        ----------
        new_name: Alias name that will be created.
        old_name: Name of pre-existing tag.
        """
        tag_lookup = await (TagLookup
            .filter(name=old_name)
            .first()
            .prefetch_related('original')
        )
        embed = disnake.Embed(color = 0x0084c7)
        if not tag_lookup:
            embed.description = f'A tag with the name of "{old_name}" does not exist.'
            return await inter.response.send_message(embed=embed,ephemeral=True)

        try:
            await TagLookup.create(
                name = new_name,
                owner_id = inter.author.id,
                original = tag_lookup.original
            )
        except IntegrityError:
            embed.description = 'A tag with this name already exists.'
        else:
            embed.description = f'Tag alias "{new_name}" that points to "{old_name}" successfully created.'
        await inter.response.send_message(embed=embed)

    @tag.sub_command(name='info')
    async def tag_info(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: str = name_param()
    ):
        """
        Shows an information about tag.
        Parameters
        ----------
        name: Requested tag name
        """
        tag = await self.get_tag(name, original=False, only=('id', 'name', 'owner_id', 'created_at', 'uses'))
        author = self.bot.get_user(tag.owner_id) or (await self.bot.fetch_user(tag.owner_id))

        embed = disnake.Embed(
            title = tag.name,
            color = 0x0084c7
        ).set_author(
            name = str(author),
            icon_url = author.display_avatar.url
        ).add_field(
            name='Owner',
            value=f'<@{tag.owner_id}>'
        )
        embed.timestamp = tag.created_at.replace(tzinfo=datetime.timezone.utc)

        if isinstance(tag, TagLookup):
            embed.set_footer(text='Alias created at')
            embed.add_field(name='Original', value=tag.original.name)
            embed.add_field(name='Lookup ID', value=tag.id, inline=False)

        elif isinstance(tag, TagTable):
            rank = await (TagTable
                .filter(uses__gt=tag.uses)
                .count()
            )
            embed.set_footer(text='Tag created at')
            embed.add_field(name='Uses', value=tag.uses)
            embed.add_field(name='Rank', value=rank+1)
            embed.add_field(name='ID', value=tag.id, inline=False)

        await inter.response.send_message(embed=embed)

    @tag.sub_command(name='all')
    async def tag_all(self, inter: disnake.ApplicationCommandInteraction):
        """
        Shows all existed tags
        """
        rows = await (TagLookup
            .all()
            .order_by('name')
            .only('id', 'name')
        )
        source = TagSource(rows)
        view = paginator.PaginatorView(source, interaction=inter)
        await view.start()

    @tag.sub_command(name='edit')
    async def tag_edit(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: str = name_param()
    ):
        """
        Edit tag owned by you.
        Parameters
        ----------
        name: Requested tag name
        """
        tag = await self.get_tag(name, only=('id', 'name', 'content', 'owner_id', 'prefix'))
        self.can_menage(inter.author, tag)

        view = TagCreateView(inter, self, tag)
        await inter.response.send_message(embed=view.prepare_embed(), view=view)
        view.message = await inter.original_message()

        if await view.wait():
            await view.message.edit(content='You took too long. Goodbye.', view=None, embed=None)
        else:
            await view.message.edit(view=None)

        if hasattr(view, 'last_interaction'):
            await (TagTable
                .filter(id=tag.id)
                .update(content=view.content)
            )
            await view.last_interaction.followup.send(f'Tag {name} successfully updated.')
    
    @tag.sub_command(name='delete')
    async def tag_delete(
        self,
        inter: disnake.ApplicationCommandInteraction,
        name: str = name_param()
    ):
        """
        Delete tag owned by you.
        Parameters
        ----------
        name: Requested tag name
        """
        tag = await self.get_tag(name, original=False, only=('id', 'owner_id'))
        self.can_menage(inter.author, tag)

        msg = str(tag)

        async def callback(value, interaction):
            if value is None:
                content = 'You took too long. Goodbye.'
            elif value:
                await tag.delete()
                content = f'{msg.capitalize()} {name} was deleted.'
            else:
                content = 'Canceled'
            
            await interaction.response.edit_message(content=content, view=None)
        
        view = Confirm(callback, listen_to=self.bot.ids(inter.author.id))
        await inter.response.send_message(f'Are you sure you wanna delete {msg} "{name}"? It cannot be undo.', view=view)


def setup(bot):
    bot.add_cog(Tags(bot))
