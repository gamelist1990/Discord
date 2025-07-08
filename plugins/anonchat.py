from discord.ext import commands
import discord
from plugins import register_command
from lib.op import OP_EVERYONE
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
            max_length=30  # 上限30文字
        )
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        text = self.message_input.value.replace('\n', ' ')
        import re
        text = re.sub(r'\s{2,}', ' ', text).strip()
        # 改行禁止
        if '\n' in self.message_input.value or '\r' in self.message_input.value:
            await interaction.followup.send("❌ 改行は禁止されています。", ephemeral=True)
            return
        # URL禁止（http, https, www, discord.gg, t.co, bit.ly なども）
        url_pattern = re.compile(r"(https?://|www\\.|discord\\.gg/|t\\.co/|bit\\.ly/|youtu\\.be/|youtube\\.com/)", re.IGNORECASE)
        if url_pattern.search(text):
            await interaction.followup.send("❌ URLの送信は禁止されています。", ephemeral=True)
            return
        # マークダウン禁止（太字・斜体・コード・引用・リンク・見出し・リスト・表・チェックボックス・画像・脚注・数式）
        markdown_pattern = re.compile(r"(\*\*.+?\*\*|__.+?__|\*.+?\*|_.+?_|`.+?`|```.+?```|>.+|\[.+?\]\(.+?\)|^#|^- |^\* |\|.+?\||!\[.+?\]\(.+?\)|\[.+?\]:|\$\$.+?\$\$|\$.+?\$)", re.MULTILINE)
        if markdown_pattern.search(text):
            await interaction.followup.send("❌ マークダウン記号の使用は禁止されています。", ephemeral=True)
            return
        # メンション禁止（@everyone, @here, <@...>, <@&...>、全角も）
        mention_pattern = re.compile(r"(@everyone|＠everyone|@here|＠here|<@!?\d+>|<@&\d+>|＠[a-zA-Z0-9_]+)")
        if mention_pattern.search(text):
            await interaction.followup.send("❌ メンションは禁止されています。", ephemeral=True)
            return
        # 連続した同一文字（8文字以上）禁止
        if re.search(r'(.)\1{7,}', text):
            await interaction.followup.send("❌ 同じ文字の連続は禁止されています。", ephemeral=True)
            return
        # 繰り返し単語（例: abc abc abc ... 4回以上、全角・半角区別せず）禁止
        if re.search(r'(\b[\wぁ-んァ-ヶ一-龠々ー]+\b)(?:\s+\1){3,}', text):
            await interaction.followup.send("❌ 同じ単語の繰り返しは禁止されています。", ephemeral=True)
            return
        # ランダムな文字列禁止（英数字のみで10文字以上、かつ辞書にない）
        if re.fullmatch(r'[A-Za-z0-9]{10,}', text):
            await interaction.followup.send("❌ ランダムな文字列は禁止されています。", ephemeral=True)
            return
        # UUID4禁止
        uuid4_pattern = re.compile(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}")
        if uuid4_pattern.search(text):
            await interaction.followup.send("❌ UUIDのような文字列は禁止されています。", ephemeral=True)
            return
        # 荒らしと思われる文（記号列や意味のない繰り返し、全角記号も）
        if re.fullmatch(r'[!-/:-@\[-`{-~！-／：-＠［-｀｛-～]{8,}', text):
            await interaction.followup.send("❌ 荒らしと思われる内容は禁止されています。", ephemeral=True)
            return
        if not text:
            await interaction.followup.send("❌ 空のメッセージは送信できません。", ephemeral=True)
            return
        channel = self.ctx.channel
        try:
            await channel.send(f"【匿名メッセージ】\n{text}")
            await interaction.followup.send("✅ 匿名でメッセージを送信しました。", ephemeral=True)
        except Exception:
            await interaction.followup.send("❌ 送信に失敗しました。", ephemeral=True)


def setup(bot):
    @commands.command()
    async def tell(ctx):
        """
        #tell ...匿名でこのチャンネルにメッセージを送信できます
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass
        embed = discord.Embed(
            title="匿名チャット",
            description="下のボタンから匿名メッセージを送信できます。",
            color=0x60a5fa
        )
        async def on_anon_button(interaction, view):
            if interaction.response.is_done():
                return
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
    register_command(bot, tell, op_level=OP_EVERYONE)
