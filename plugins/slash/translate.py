import discord
from plugins import registerMessageCommand
import requests


async def translate_message(interaction: discord.Interaction, message: discord.Message):
    text = message.content.strip()
    if not text:
        await interaction.response.send_message("❌ 翻訳するテキストがありません。", ephemeral=True)
        return
    try:
        # まず「考え中…」の一時メッセージを送信
       # print(f"[DEBUG] 翻訳開始: text='{text}'")
        await interaction.response.send_message("🤔 翻訳中…", ephemeral=True)

        # ひらがな・カタカナが含まれていれば日本語、それ以外は英語とみなす
        if any(c for c in text if '\u3040' <= c <= '\u30ff'):
            lang = "ja"
            target = "en"
        else:
            lang = "en"
            target = "ja"
        url = "https://script.google.com/macros/s/AKfycbxPh_IjkSYpkfxHoGXVzK4oNQ2Vy0uRByGeNGA6ti3M7flAMCYkeJKuoBrALNCMImEi_g/exec"
        payload = {"text": text, "from": lang, "to": target}
        headers = {"Content-Type": "application/json"}
        #print(f"[DEBUG] POST {url} payload={payload}")
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        #print(f"[DEBUG] status={resp.status_code} response={resp.text}")
        resp.raise_for_status()
        data = resp.json()
        translated = data.get("translation")
        #print(f"[DEBUG] 翻訳結果: {translated}")
        if not translated:
            raise Exception("翻訳結果が取得できませんでした。")

        # Markdown判定による自動code block囲みを廃止し、そのまま表示
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

        # 画像のみのメッセージの場合は画像もEmbedに表示
        if message.attachments:
            # 最初の画像のみ表示（複数ある場合）
            for att in message.attachments:
                if att.content_type and att.content_type.startswith("image"):
                    embed.set_image(url=att.url)
                    break

        # 一時メッセージを「翻訳完了」に編集し、その後Embedを表示
        await interaction.edit_original_response(content="✅ 翻訳完了", embed=embed)
    except Exception as e:
        error_msg = f"❌ 翻訳に失敗しました: {e}"
        print(error_msg)
        # 既存の一時メッセージをエラー表示に編集
        try:
            await interaction.edit_original_response(content=error_msg, embed=None)
        except Exception as ee:
            print(f"[DEBUG] edit_original_response failed: {ee}")

def setup(bot):
    registerMessageCommand(
        bot,
        name="翻訳/Translate",
        callback=translate_message
    )
