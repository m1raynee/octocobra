from typing import Any, Callable, Coroutine, Sequence, Tuple, Union, Optional
from disnake import (
    ui,
    MessageInteraction,
    ButtonStyle
)
from .emojis import accept_mark, deny_mark

class _BaseView(ui.View):
    def __init__(
        self,
        *,
        author_id: int,
        timeout: Optional[float] = 180.
    ):
        if not author_id:
            raise TypeError('listen_to cannot be with zero length')
        super().__init__(timeout=timeout)
        self.author_id = author_id

    async def interaction_check(self, interaction: MessageInteraction) -> bool:
        if (
            (interaction.author and interaction.author.id == self.author_id) or
            (interaction.bot    and interaction.author.id in interaction.bot.owner_ids)
        ):
            return True
        await interaction.response.send_message('You cannot interact with this menu.', ephemeral=True)
        return False


confirm_emojis = {
    True: accept_mark,
    False: deny_mark
}

class ConfirmButton(ui.Button['Confirm']):
    def __init__(self, value: bool, *, style: ButtonStyle = ..., label: Optional[str] = None):
        super().__init__(style=style, label=label, emoji=confirm_emojis[bool(value)])
        self.value = value

    async def callback(self, interaction: MessageInteraction):
        await interaction.response.defer()
        self.view.value = self.value
        self.view.stop()

class Confirm(_BaseView):
    def __init__(self, *, author_id: int, timeout: Optional[float] = 180.):
        super().__init__(author_id=author_id, timeout=timeout)
        self.value = None

        self.add_item(ConfirmButton(True, style=ButtonStyle.green))
        self.add_item(ConfirmButton(False, style=ButtonStyle.red))
    
    async def start(self) -> Optional[bool]:
        await self.wait()
        return self.value

class Delete(_BaseView):
    def __init__(self, *, author_id: int, timeout: Optional[float] = 180.):
        super().__init__(author_id=author_id, timeout=timeout)
    
    @ui.button(
        label='Delete',
        emoji='\N{WASTEBASKET}'
    )
    async def delete_button(self, _, interaction: MessageInteraction):
        await interaction.response.defer()
        await interaction.delete_original_message()