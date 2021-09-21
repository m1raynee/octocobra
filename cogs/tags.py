import asyncio
import datetime
from os import name
from typing import Dict, Union, List

from discord.ext import menus
from disnake.ext import commands
from disnake import ui
import disnake
from tortoise.exceptions import IntegrityError

from .utils.db import in_transaction, TransactionWrapper, F
from .utils.db.tags import TagTable, TagLookup
from .utils.helpers import safe_send_prepare
from .utils import paginator


class FakeUser(disnake.Object):
    avatar = None

    @property
    def display_name(self):
        return str(self.id)

    def __str__(self):
        return str(self.id)

class FakeMessage(disnake.Object):
    "kinda hacky thing"
    def __init__(self, inter: disnake.ApplicationCommandInteraction):
        super().__init__(0)
        data = inter.data
        resolved = data.resolved

        self.content = f"/{data.name} {' '.join([f'{k}: {v}' for k,v in data.options.items()])}"
        self.mentions = [*resolved.members.values(), *resolved.users.values()]
        self.role_mentions = list(resolved.roles.values())
        inter.message = self  # insert message to interaction

class TagName(commands.clean_content):
    async def convert(self, ctx, argument: str) -> str:
        if not hasattr(ctx, 'message'):
            FakeMessage(ctx)
        converted = await super().convert(ctx, argument)
        lower = converted.lower().strip()

        if not lower:
            raise commands.BadArgument('Missing tag name.')

        if len(lower) > 50:
            raise commands.BadArgument('Tag name must be in range from 3 to 50.')

        return lower

class TagMember(commands.Converter):
    async def convert(self, ctx, argument) -> Union[disnake.Member, FakeUser]:
        if not hasattr(ctx, 'message'):
            FakeMessage(ctx)
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument as e:
            if argument.isdigit():
                return FakeUser(id=int(argument))
            raise

class CreateView(disnake.ui.View):
    message: disnake.Message

    def __init__(self, bot: commands.Bot, init_interaction: disnake.Interaction, cog: 'Tags'):
        super().__init__(timeout=300)
        self.bot = bot
        self.init_interaction = init_interaction
        self.cog = cog

        self.name = None
        self.content = None

        self.message = None
        self.is_aborted = False
        self.converter = TagName()

    def response_check(self, msg):
        return msg.channel == self.message.channel and msg.author == self.init_interaction.author

    def prepare_embed(self):
        desc = (
            'Press "Confirm" to end this shit\n'
            'Press "Name" to make name, "Content" to make content\n'
            'Press "Abort" to abort.'
        )
        if len(self.content) > 1024:
            desc += '\n**Hint:** Tag content reached embed field limitation, this will not affect the content'
        return disnake.Embed(
            title='Tag creation',
            description=desc,
            color=0x0084c7
        ).add_field(
            name='Name', value=self.name, inline=False
        ).add_field(
            name='Content', value=self.content[:1024], inline=False
        )

    def disable_all(self):
        for child in self.children:
            if child.label == 'Abort':
                continue
            child.disabled = True

    def enable_all(self):
        for child in self.children:
            if child.label != 'Abort':
                child.disabled = False
            if child.label == 'Confirm':
                if (self.name is not None) and (self.content is not None):
                    child.disabled = False
                else:
                    child.disabled = True

    async def interaction_check(self, interaction: disnake.Interaction) -> bool:
        if interaction.author != self.init_interaction.author:
            await interaction.response.send_message('You\'re not an author of this View.', ephemeral=True)
            return False
        return True

    @ui.button(
        label='Name',
        style=disnake.ButtonStyle.secondary
    )
    async def name_button(self, button: disnake.Button, interaction: disnake.Interaction):
        self.disable_all()
        msg_content = 'Cool, let\'s make a name. Send the tag name in the next message...'

        await interaction.response.edit_message(content=msg_content, view=self)
        msg = await self.bot.wait_for('message', check=self.response_check, timeout=60)

        content = ''
        try:
            fake_ctx = commands.Context(message=msg, bot=self.bot, view=None)
            name = await self.converter.convert(fake_ctx, msg.content)
        except commands.BadArgument as e:
            content = f'{e}. Press "Name" to retry.'
        else:
            if self.cog.is_tag_being_made(name):
                content = 'Sorry. This tag is currently being made by someone.'
            else:
                rows = await (TagTable
                    .filter(name=name)
                    .limit(1)
                )
                if len(rows) == 0:
                    self.name = name
                    self.cog.add_in_progress_tag(name)
                    self.remove_item(button)
                else:
                    content='Sorry. A tag with that name already exists.'

        self.enable_all()
        await self.message.edit(content=content, embed=self.prepare_embed(), view=self)
    
    @ui.button(
        label='Content',
        style=disnake.ButtonStyle.secondary
    )
    async def content_button(self, button: disnake.Button, interaction: disnake.Interaction):
        self.disable_all()
        msg_content = 'Cool, let\'s make a content. Send the tag content in the next message...'

        await interaction.response.edit_message(content=msg_content, view=self)
        msg = await self.bot.wait_for('message', check=self.response_check, timeout=300)
        fake_ctx = commands.Context(message=msg, bot=self.bot, view=None)

        if msg.content:
            clean_content = await commands.clean_content().convert(fake_ctx, msg.content)
        else:
            clean_content = msg.content

        if msg.attachments:
            clean_content += f'\n{msg.attachments[0].url}'

        if len(clean_content) > 2000:
            await self.message.edit('Tag content is a maximum of 2000 characters.')
        else:
            self.content = clean_content

        self.enable_all()
        await self.message.edit(content='', embed=self.prepare_embed(), view=self)

    @ui.button(
        label='Confirm',
        style=disnake.ButtonStyle.success,
        disabled=True
    )
    async def comfirm_button(self, button: disnake.Button, interaction: disnake.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        self.last_interaction = interaction
        self.cog.remove_in_progress_tag(self.name)
        self.stop()
    
    @ui.button(
        label='Abort',
        style=disnake.ButtonStyle.danger
    )
    async def abort_button(self, button: disnake.Button, interaction: disnake.Interaction):
        self.cog.remove_in_progress_tag(name)
        await interaction.response.edit_message(content='Tag creation aborted o/', view=None, embed=None)
        self.stop()

    async def on_error(self, error: Exception, item, interaction: disnake.Interaction) -> None:
        if isinstance(error, asyncio.TimeoutError):
            if interaction.response.is_done():
                method = self.message.edit
            else:
                method = interaction.response.edit_message
            if self.name is not None:
                self.cog.remove_in_progress_tag(self.name)
            await method(content='You took too long. Goodbye.', view=None, embed=None)
            return self.stop()
        raise error

class TagSource(paginator.BaseListSource):
    entries: List[TagLookup]
    def __init__(self, entries: List[TagLookup]):
        super().__init__(entries, 20)

    async def format_page(self, view: paginator.PaginatorView, page: List[TagLookup]) -> Union[disnake.Embed, str, dict]:
        e = self.base_embed()
        e.description = '\n'.join([
            f'{i}. {row.name} (id: {row.id})'
            for i, row
            in enumerate(page, view.current_page*self.per_page+1)
        ])
        return e

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
    
    async def create_tag(self, inter: disnake.Interaction, name, content):
        name= name.lower()
        async with in_transaction() as tr:
            tr: TransactionWrapper
            try:
                tag = await TagTable.create(
                    name = name,
                    content = content,
                    owner_id = inter.author.id
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

    def is_tag_being_made(self, name):
        return name.lower() in self._tags_being_made
    def add_in_progress_tag(self, name):
        self._tags_being_made.add(name.lower())
    def remove_in_progress_tag(self, name):
        self._tags_being_made.discard(name.lower())


    @commands.slash_command(description='Tag sub-command group')
    async def tag(self, inter):
        pass

    @tag.sub_command(
        name = 'show',
        description = 'Search for a tag',
        options = [
            disnake.Option('name', 'Requested tag name', disnake.OptionType.string, True),
            disnake.Option(
                'type', 
                'Whether what content type will be shown', 
                choices=[
                    disnake.OptionChoice('Rich', 'rich'),
                    disnake.OptionChoice('Raw', 'raw')
                ]
            )
        ]
    )
    async def tag_show(self, inter: disnake.ApplicationCommandInteraction, name, type=None):
        name = await TagName().convert(inter, name)

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
    
    @tag.sub_command(
        name = 'create',
        description = 'Creates a new tag owned by you (interactive !!)',
    )
    async def tag_create(self, inter: disnake.ApplicationCommandInteraction):
        view = CreateView(self.bot, inter, self)
        await inter.response.send_message(embed=view.prepare_embed(), view=view)
        view.message = await inter.original_message()

        if await view.wait():
            if view.name is not None:
                self.remove_in_progress_tag(view.name)
            return await view.message.edit(content='You took too long. Goodbye.', view=None, embed=None)
        
        await view.message.edit(view=None)
        if hasattr(view, 'last_interaction'):
            await self.create_tag(view.last_interaction, view.name, view.content)

    @tag.sub_command(
        name = 'alias',
        description = 'Creates an alias for a pre-existing tag.',
        options = [
            disnake.Option('new_name', 'Alias name that will be created.', disnake.OptionType.string, True),
            disnake.Option('old_name', 'Name of pre-existing tag.', disnake.OptionType.string, True)
        ]
    )
    async def tag_alias(self, inter: disnake.ApplicationCommandInteraction, new_name, old_name):
        converter = TagName()
        new_name = await converter.convert(inter, new_name)
        old_name = await converter.convert(inter, old_name)

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

    @tag.sub_command(
        name = 'info',
        description = 'Shows an information about tag.',
        options = [disnake.Option('name', 'Requested tag name', disnake.OptionType.string, True)]
    )
    async def tag_info(self, inter: disnake.ApplicationCommandInteraction, name):
        name = await TagName().convert(inter, name)
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

    @tag.sub_command(
        name = 'all',
        description = 'Shows all existed tags'
    )
    async def tag_stats(self, inter: disnake.ApplicationCommandInteraction):
        rows = await (TagLookup
            .all()
            .order_by('name')
        )
        source = TagSource(rows)
        view = paginator.PaginatorView(source, interaction=inter)
        await view.start()


def setup(bot):
    bot.add_cog(Tags(bot))
