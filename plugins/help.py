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
        embed = Embed(
            title=f"📖 利用可能なコマンド一覧 (Page {self.page+1}/{self.max_page+1})",
            description="**コマンド名** と _説明_ をご確認ください。",
            color=0x4ade80
        )
        for cmd in cmds_page:
            # コマンド名と説明を分離
            if cmd.startswith("`"):
                try:
                    name, desc = cmd.split(':', 1)
                except ValueError:
                    name, desc = cmd, ''
                name = name.strip('` ')
                desc = desc.strip()
                # Markdownでコマンド本体を強調、説明はイタリック
                embed.add_field(
                    name=f"`{name}`",
                    value=f"*{desc or '説明なし'}*",
                    inline=False
                )
            else:
                embed.add_field(name=cmd, value='*説明なし*', inline=False)
        embed.set_footer(text="Botに関する質問は管理者まで。 | Powered by Discord.py")
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
    async def help(ctx, *args):
        """
        利用可能なコマンド一覧をEmbedでページ式表示します。
        #help <コマンド名> で個別説明も表示できます。
        """
        cmd_name = args[0] if args else None
        if cmd_name:
            # コマンド名で個別説明
            cmd = ctx.bot.get_command(cmd_name)
            if cmd:
                embed = Embed(
                    title=f"`{ctx.prefix}{cmd.name}` の説明",
                    description=cmd.help or '説明なし',
                    color=0x4ade80
                )
                await ctx.send(embed=embed, delete_after=30)
            else:
                await ctx.send(f"❌ コマンド `{cmd_name}` は見つかりませんでした。", delete_after=10)
            return
        cmds = [f"`{ctx.prefix}{c.name}`: {c.help or '説明なし'}" for c in ctx.bot.commands]
        view = HelpPageView(ctx, cmds)
        embed = view.get_embed()
        await ctx.send(embed=embed, view=view)
    register_command(bot, help, aliases=['h'], admin=False)
