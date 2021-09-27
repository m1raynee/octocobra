from typing import Callable, Coroutine, Iterable, List, Union, Optional
import disnake

class _BaseView(disnake.ui.View):
    def __init__(self, *, listen_to: Iterable[int] = [], timeout: Optional[float] = 180):
        if len(listen_to) == 0:
            raise TypeError('listen_to cannot be with zero length')
        super().__init__(timeout=timeout)
        self.listen_to = listen_to

    async def interaction_check(self, interaction: disnake.MessageInteraction) -> bool:
        if interaction.author and interaction.author.id in self.listen_to:
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
            Coroutine[None]
        ],
        *,
        listen_to: Iterable[int]
    ):
        super().__init__(listen_to=listen_to, timeout=180)
        self.value = None
        self.callback = callback

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
        await self.stop()