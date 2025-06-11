from discord.ext import commands
import discord
from plugins import register_command
from plugins.common_ui import ModalInputView

# 匿名チャットプラグイン

class AnonChatModal(discord.ui.Modal):
    def __init__(self, ctx):
        super().__init__(title="匿名メッセージ送信")
        self.ctx = ctx
        self.message_input = discord.ui.TextInput(
            label="送信する内容",
            placeholder="ここに匿名で送りたい内容を入力...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=500
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # 匿名でメッセージを送信（PEXserver名義で）
        channel = self.ctx.channel
        try:
            await channel.send(f"【匿名メッセージ】\n{self.message_input.value}")
            await interaction.followup.send("✅ 匿名でメッセージを送信しました。", ephemeral=True)
        except Exception:
            await interaction.followup.send("❌ 送信に失敗しました。", ephemeral=True)


def setup(bot):
    @commands.command()
    async def tell(ctx):
        """
        #tell ...匿名でこのチャンネルにメッセージを送信できます
        """
        embed = discord.Embed(
            title="匿名チャット",
            description="下のボタンから匿名メッセージを送信できます。",
            color=0x60a5fa
        )
        async def on_anon_button(interaction, view):
            await interaction.response.send_modal(AnonChatModal(ctx))
        view = ModalInputView(
            label="チャットする",
            on_button=on_anon_button,
            button_emoji="💬",
            style=discord.ButtonStyle.primary,
            allowed_user_id=ctx.author.id,
            auto_delete_on_button=True
        )
        await ctx.send(embed=embed, view=view)
    register_command(bot, tell, aliases=None, admin=False)
