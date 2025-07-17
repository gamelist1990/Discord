import discord
from plugins import registerMessageCommand

class UrlConvertModal(discord.ui.Modal, title="URL変換"):
    url = discord.ui.TextInput(
        label="YouTube/Twitter/XのURLを入力",
        style=discord.TextStyle.short,
        placeholder="https://www.youtube.com/watch?v=... または https://twitter.com/...",
        required=True,
        max_length=200
    )

    def __init__(self, interaction: discord.Interaction):
        super().__init__()
        self.interaction = interaction

    async def on_submit(self, interaction: discord.Interaction):
        input_url = self.url.value.strip()
        result = convert_url(input_url)
        await interaction.response.send_message(result, ephemeral=True)

def convert_url(url: str) -> str:
    # YouTube
    if "youtube.com/watch?v=" in url or "youtu.be/" in url:
        import re, requests
        video_id = None
        if "youtube.com/watch?v=" in url:
            m = re.search(r"v=([\w-]{11})", url)
            if m:
                video_id = m.group(1)
        elif "youtu.be/" in url:
            m = re.search(r"youtu.be/([\w-]{11})", url)
            if m:
                video_id = m.group(1)
        if video_id:
            base_url = "https://pexsabas.onrender.com/"  # fallback
            return f"YouTube埋め込み用URL: {base_url}/youtube/{video_id}"
        else:
            return "❌ 有効なYouTube動画URLではありません。"
    # Twitter/X
    import re
    if "twitter.com/" in url:
        # twitter.com/username/status/123...
        m = re.match(r"https?://twitter.com/([\w_]+)/status/([0-9]+)", url)
        if m:
            username, tweet_id = m.group(1), m.group(2)
            return f"FxTwitter埋め込み用URL: https://fxtwitter.com/{username}/status/{tweet_id}"
        else:
            return "❌ 有効なTwitterツイートURLではありません。"
    if "x.com/" in url:
        # x.com/username/status/123...
        m = re.match(r"https?://x.com/([\w_]+)/status/([0-9]+)", url)
        if m:
            username, tweet_id = m.group(1), m.group(2)
            return f"FixupX埋め込み用URL: https://fixupx.com/{username}/status/{tweet_id}"
        else:
            return "❌ 有効なX.comツイートURLではありません。"
    return "❌ サポートされていないURL形式です。"

async def convert_url_command(interaction: discord.Interaction, message: discord.Message):
    # Modalを表示
    modal = UrlConvertModal(interaction)
    await interaction.response.send_modal(modal)

def setup(bot):
    registerMessageCommand(
        bot,
        name="url/変換",
        callback=convert_url_command
    )
