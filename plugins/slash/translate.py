import discord
from plugins import registerMessageCommand
import requests

# 無料の翻訳API LibreTranslateを利用（APIキー不要・制限あり）
TRANSLATE_API_URL = "https://libretranslate.de/translate"

async def translate_message(interaction: discord.Interaction, message: discord.Message):
    text = message.content.strip()
    if not text:
        await interaction.response.send_message("❌ 翻訳するテキストがありません。", ephemeral=True)
        return
    try:
        # ひらがな・カタカナが含まれていれば日本語、それ以外は英語とみなす
        if any(c for c in text if '\u3040' <= c <= '\u30ff'):
            lang = "ja"
            target = "en"
        else:
            lang = "en"
            target = "ja"
        from urllib.parse import quote
        url = f"https://script.google.com/macros/s/AKfycbxPh_IjkSYpkfxHoGXVzK4oNQ2Vy0uRByGeNGA6ti3M7flAMCYkeJKuoBrALNCMImEi_g/exec?text={quote(text)}&from={lang}&to={target}"
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        translated = data.get("translation")
        if not translated:
            raise Exception("翻訳結果が取得できませんでした。")
        embed = discord.Embed(
            title=f"翻訳 {lang} → {target}",
            description=translated,
            color=0x3498db
        )
        # メッセージ送信者のアバターと名前を表示
        author = message.author
        avatar_url = None
        if hasattr(author, 'display_avatar'):
            avatar = getattr(author, 'display_avatar', None)
            avatar_url = getattr(avatar, 'url', None)
        if not avatar_url and hasattr(author, 'avatar'):
            avatar = getattr(author, 'avatar', None)
            avatar_url = getattr(avatar, 'url', None)
        if not avatar_url:
            avatar_url = ""
        embed.set_author(
            name=f"{getattr(author, 'display_name', getattr(author, 'name', ''))}",
            icon_url=avatar_url
        )
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )
    except Exception as e:
        error_msg = f"❌ 翻訳に失敗しました: {e}"
        try:
            await interaction.response.send_message(error_msg, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send(error_msg, ephemeral=True)
            except Exception:
                print(error_msg)

def setup(bot):
    registerMessageCommand(
        bot,
        name="翻訳/Translate",
        callback=translate_message
    )
