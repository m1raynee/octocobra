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
        await inter.response.defer()
        self.stop()
    
    @disnake.ui.button(
        label='Cancel',
        style=disnake.ButtonStyle.danger
    )
    async def do_cancel(self, _, inter: disnake.ApplicationCommandInteraction):
        self.value = False
        await inter.response.defer()
        self.stop()