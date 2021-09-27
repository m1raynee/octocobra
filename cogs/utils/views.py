import disnake

class Confirm(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.value = None
    
    @disnake.ui.button(
        label='Confirm',
        style=disnake.ButtonStyle.success
    )
    async def do_confirm(self, _, inter: disnake.ApplicationCommandInteraction):
        self.value = True
        self.inter = inter
        self.stop()
    
    @disnake.ui.button(
        label='Cancel',
        style=disnake.ButtonStyle.success
    )
    async def do_cancel(self, _, inter: disnake.ApplicationCommandInteraction):
        self.value = False
        self.inter = inter
        self.stop()
    
    async def start(self):
        await self.wait()
        return self.value