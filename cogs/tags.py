import asyncio
from dataclasses import FrozenInstanceError
from os import name
from typing import TYPE_CHECKING

from disnake.ext import commands
from disnake import ui
import disnake
from tortoise.exceptions import IntegrityError

from .utils import db
from bot import DisnakeHelper


class TagTable(db.Model):
    id = db.IntField(pk=True)
    name = db.CharField(50, unique=True)

    content = db.TextField()
    owner_id = db.BigIntField()
    uses = db.IntField(default=0)
    created_at = db.DatetimeField(auto_now_add=True)

    aliases: db.ForeignKeyRelation['TagLookup']

    class Meta:
        table = 'tags'

class TagLookup(db.Model):
    id = db.IntField(pk=True)
    name = db.CharField(50, unique=True)
    original = db.ForeignKeyField('tags.TagTable', 'aliases')

    owner_id = db.BigIntField()
    created_at = db.DatetimeField(auto_now_add=True)

    class Meta:
        table = 'tagslookup'

class TagName(commands.clean_content):
    async def convert(self, ctx, argument: str) -> str:
        if not hasattr(ctx, 'message'):
            ctx.message = FakeMessage(ctx)
        converted = await super().convert(ctx, argument)
        lower = converted.lower().strip()

        if not lower:
            raise commands.BadArgument('Missing tag name.')

        if len(lower) not in range(3, 51):
            raise commands.BadArgument('Tag name must be in range from 3 to 50.')

        return lower

class FakeUser(disnake.Object):
    class FakeAsset:
        url = 'https://cdn.discordapp.com/embed/avatars/0.png'

        def __str__(self):
            return self.url

    @property
    def avatar(self):
        return self.FakeAsset()

    @property
    def display_name(self):
        return str(self.id)

    def __str__(self):
        return str(self.id)

class FakeMessage(disnake.Object):
    def __init__(self, inter: disnake.ApplicationCommandInteraction):
        super().__init__(0)
        data = inter.data
        self.content = f"/{data.name} {' '.join([f'{k}: {v}' for k,v in data.options.items()])}"
    @property
    def mentions(self):
        return []
    @property
    def role_mentions(self):
        return []

class TagMember(commands.Converter):
    async def convert(self, ctx, argument) -> disnake.Member:
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument as e:
            if argument.isdigit():
                return FakeUser(id=int(argument))
            raise e

class CreateView(disnake.ui.View):
    message: disnake.Message

    def __init__(self, bot: DisnakeHelper, init_interaction: disnake.Interaction, cog: 'Tags'):
        super().__init__(timeout=60)
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
        return disnake.Embed(
            title='Tag creation',
            description=(
                'Press "Confirm" to end this shit\n'
                'Press "Name" to make name, "Content" to make content\n'
                'Press "Abort" to abort.'
            ),
            color=0x0084c7
        ).add_field(
            name='Name', value=self.name, inline=False
        ).add_field(
            name='Content', value=self.content, inline=False
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
            await interaction.response.send_message('You\'re not an author of this View.')
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
        await interaction.response.edit_message(content='Tag creation aborted o/', view=ui.View(), embed=None)
        self.stop()

    async def on_error(self, error: Exception, item, interaction: disnake.Interaction) -> None:
        if isinstance(error, asyncio.TimeoutError):
            if interaction.response.is_done():
                method = self.message.edit
            else:
                method = interaction.response.edit_message
            if self.name is not None:
                self.cog.remove_in_progress_tag(self.name)
            await method(content='You took too long. Goodbye.', view=ui.View(), embed=None)
            return self.stop()
        raise error


class Tags(commands.Cog):
    """Commands to fetch something by a tag name"""

    def __init__(self, bot):
        self.bot: DisnakeHelper = bot
        self._reserved_tags_being_made = set()

    async def get_tag(self, name: str) -> TagTable:
        def not_found(rows):
            if rows is None or len(rows) == 0:
                raise RuntimeError('Tag not found.')

            names = '\n'.join(r.name for r in rows)
            raise RuntimeError(f'Tag not found. Did you mean...\n{names}')

        tag = await (TagTable
            .filter(name=name)
            .only('id', 'name', 'content')
            .first()
        )
        if not tag:
            tag = await (TagLookup
                .filter(name=name)
                .prefetch_related('original')
                .first()
            )
            if not tag:
                query = await (TagLookup
                    .filter(name__contains=name)
                    .limit(3)
                    .only('name')
                )
                not_found(query)
            tag = tag.original

        return tag
    
    async def create_tag(self, inter: disnake.Interaction, name, content):
        name= name.lower()
        async with db.in_transaction() as tr:
            tr: db.TransactionWrapper
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
        return name.lower() in self._reserved_tags_being_made
    def add_in_progress_tag(self, name):
        self._reserved_tags_being_made.add(name.lower())
    def remove_in_progress_tag(self, name):
        self._reserved_tags_being_made.discard(name.lower())


    @commands.slash_command(description='Tag sub-command group')
    async def tag(self, inter):
        pass

    @tag.sub_command(
        name = 'show',
        description = 'Search for a tag',
        options = [disnake.Option('name', 'Requested tag name', disnake.OptionType.string, True)]
    )
    async def tag_show(self, inter: disnake.ApplicationCommandInteraction, name):
        name = await TagName().convert(inter, name)
        try:
            tag = await self.get_tag(name)
        except RuntimeError as e:
            return await inter.response.send_message(e, ephemeral=True)
        
        await inter.response.send_message(tag.content)
        await (TagTable
            .filter(id=tag.id)
            .update(uses = db.F('uses') + 1)
        )
    
    @tag.sub_command(
        name = 'create',
        description = 'Creates a new tag owned by you (interactive !!)',
    )
    async def tag_create(self, inter: disnake.Interaction):
        view = CreateView(self.bot, inter, self)
        await inter.response.send_message(embed=view.prepare_embed(), view=view)
        view.message = await inter.original_message()

        if await view.wait():
            return await view.message.edit(content='You took too long. Goodbye.', view=ui.View(), embed=None)
        else:
            await view.message.edit(view=ui.View())
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
    async def tag_alias(self, inter: disnake.Interaction, new_name, old_name):
        converter = TagName()
        new_name = await converter.convert(inter, new_name)
        old_name = await converter.convert(inter, old_name)

        tag_lookup = await (TagLookup
            .filter(name=old_name)
            .first()
            .prefetch_related('original')
        )
        if not tag_lookup:
            return await inter.response.send_message(f'A tag with the name of "{old_name}" does not exist.')
        try:
            await TagLookup.create(
                name = new_name,
                owner_id = inter.author.id,
                original = tag_lookup.original
            )
        except IntegrityError:
            await inter.response.send_message('A tag with this name already exists.')
        else:
            await inter.response.send_message(f'Tag alias "{new_name}" that points to "{old_name}" successfully created.')


def setup(bot):
    bot.add_cog(Tags(bot))
