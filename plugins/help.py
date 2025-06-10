from discord import Embed, Interaction, ButtonStyle
from discord.ui import View, Button
from discord.ext import commands
from plugins import register_command

class HelpPageView(View):
    def __init__(self, ctx, cmds, per_page=10):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.cmds = cmds
        self.per_page = per_page
        self.page = 0
        self.max_page = (len(cmds) - 1) // per_page
        self.author_id = ctx.author.id
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if self.max_page > 0 and self.page > 0:
            self.add_item(self.PrevButton(self))
        if self.max_page > 0 and self.page < self.max_page:
            self.add_item(self.NextButton(self))

    def get_embed(self):
        start = self.page * self.per_page
        end = start + self.per_page
        cmds_page = self.cmds[start:end]
        desc = '\n'.join(cmds_page)
        embed = Embed(
            title=f"利用可能なコマンド一覧 (Page {self.page+1}/{self.max_page+1})",
            description=desc or 'コマンドがありません',
            color=0x4ade80
        )
        return embed

    class PrevButton(Button):
        def __init__(self, parent):
            super().__init__(label="前へ", style=ButtonStyle.secondary)
            self.parent = parent
        async def callback(self, interaction: Interaction):
            if interaction.user.id != self.parent.author_id:
                await interaction.response.send_message("❌ あなたは操作できません。", ephemeral=True)
                return
            self.parent.page -= 1
            self.parent.update_buttons()
            await interaction.response.edit_message(embed=self.parent.get_embed(), view=self.parent)

    class NextButton(Button):
        def __init__(self, parent):
            super().__init__(label="次へ", style=ButtonStyle.primary)
            self.parent = parent
        async def callback(self, interaction: Interaction):
            if interaction.user.id != self.parent.author_id:
                await interaction.response.send_message("❌ あなたは操作できません。", ephemeral=True)
                return
            self.parent.page += 1
            self.parent.update_buttons()
            await interaction.response.edit_message(embed=self.parent.get_embed(), view=self.parent)

def setup(bot):
    @commands.command()
    async def help(ctx):
        """
        利用可能なコマンド一覧をEmbedでページ式表示します。
        """
        cmds = [f"`{ctx.prefix}{c.name}`: {c.help or '説明なし'}" for c in ctx.bot.commands]
        view = HelpPageView(ctx, cmds)
        embed = view.get_embed()
        await ctx.send(embed=embed, view=view)
    register_command(bot, help, aliases=['h'], admin=False)
