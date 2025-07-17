import discord
from plugins import registerSlashCommand

import requests
from PIL import Image, ImageDraw, ImageFont
import io
import re
from plugins.common_ui import ModalInputView

# ユーザーインストール型 /url コマンド

def setup(bot):
    async def on_submit(interaction, value, recipient, view):
        url = value.strip()
        url_pattern = re.compile(r"^https?://[\w/:%#\$&\?\(\)~\.\=\+\-]+$")
        if not url or not url_pattern.match(url):
            await interaction.response.send_message("❌ 有効なURLを入力してください。", ephemeral=True)
            return
        # TwitterまたはX.comの場合は公式推奨のFxEmbed URLに自動変換して貼るだけ
        twitter_match = re.match(r"^(https?://)(www\.)?twitter\.com/", url, re.IGNORECASE)
        x_match = re.match(r"^(https?://)(www\.)?x\.com/", url, re.IGNORECASE)
        if twitter_match:
            fx_url = re.sub(r"^(https?://)(www\.)?twitter\.com/", r"https://fxtwitter.com/", url, flags=re.IGNORECASE)
            await interaction.response.send_message(f"**FxTwitterプレビュー：**\n{fx_url}", ephemeral=False)
            return
        elif x_match:
            fx_url = re.sub(r"^(https?://)(www\.)?x\.com/", r"https://fixupx.com/", url, flags=re.IGNORECASE)
            await interaction.response.send_message(f"**FixupXプレビュー：**\n{fx_url}", ephemeral=False)
            return
        # それ以外は通常通りプレビュー生成
        await interaction.response.send_message("⏳ プレビュー生成中...", ephemeral=False)
        message = await interaction.original_response()
        thumb_url = f"https://image.thum.io/get/{url}"
        try:
            resp = requests.get(thumb_url, timeout=10)
            resp.raise_for_status()
            img_bytes = io.BytesIO(resp.content)
            img_bytes.seek(0)
            file = discord.File(img_bytes, filename="thumbnail.png")
            await message.edit(
                content=f"**プレビュー：**\n{url}",
                attachments=[file]
            )
        except Exception as e:
            error_msg = f"❌ プレビュー画像の取得に失敗しました: {e}"
            try:
                await message.edit(content=error_msg, attachments=[])
            except Exception:
                try:
                    await interaction.followup.send(error_msg, ephemeral=True)
                except Exception:
                    print(error_msg)

    async def url_callback(interaction: discord.Interaction):
        view = ModalInputView(
            label="URLを入力",
            modal_title="WebページURL入力",
            text_label="URLを入力してください",
            placeholder="https://google.com/",
            input_style="paragraph",
            min_length=5,
            max_length=300,
            on_submit=on_submit,
            ephemeral=True,
            allowed_user_id=interaction.user.id,
            show_modal_direct=True
        )
        await view.send_or_modal(interaction, content="取得したいWebページのURLを入力してください。", ephemeral=True)

    registerSlashCommand(
        bot,
        "url",
        "指定したURLのHTML先頭部を表示し、URL画像を添付します。",
        url_callback,
        user=True
    )
