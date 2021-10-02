from typing import Any, Callable, Coroutine, Iterable, List, Tuple, Union, Optional
import disnake

class _BaseView(disnake.ui.View):
    def __init__(
        self,
        *,
        listen_to: Iterable[int] = [],
        timeout: Optional[float] = 180
    ):
        if len(listen_to) == 0:
            raise TypeError('listen_to cannot be with zero length')
        super().__init__(timeout=timeout)
        self.listen_to = listen_to

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if (
            (interaction.author and interaction.author.id in self.listen_to) or
            (interaction.author.id in interaction.bot.owner_ids)
        ):
            return True
        await interaction.response.send_message('You cannot interact with this menu.', ephemeral=True)
        return False

class Confirm(_BaseView):
    def __init__(
        self,
        callback: Callable[
            [
                Union[bool, None],
                disnake.MessageInteraction
            ],
            Coroutine[Any, Any, Any]
        ],
        *,
        listen_to: Iterable[int] = [],
        labels: Tuple[str, str] = ('Confirm', 'Cancel')
    ):
        super().__init__(listen_to=listen_to)
        self.value = None
        self.callback = callback

        self.do_confirm.label, self.do_cancel.label = labels

    @disnake.ui.button(
        label='Confirm',
        style=disnake.ButtonStyle.success
    )
    async def do_confirm(self, _, inter: disnake.MessageInteraction):
        self.value = True
        await self.finalize(inter)

    @disnake.ui.button(
        label='Cancel',
        style=disnake.ButtonStyle.danger
    )
    async def do_cancel(self, _, inter: disnake.MessageInteraction):
        self.value = False
        await self.finalize(inter)

    async def finalize(self, inter):
        await self.callback(self.value, inter)
        self.stop()

class Delete(_BaseView):
    def __init__(self, *, listen_to: Iterable[int] = [], timeout: Optional[float] = 180):
        super().__init__(listen_to=listen_to, timeout=timeout)
    
    @disnake.ui.button(
        label='Delete',
        emoji='\N{WASTEBASKET}'
    )
    async def delete_button(self, _, interaction: disnake.MessageInteraction):
        await interaction.response.defer()
        await interaction.message.delete()