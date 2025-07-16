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
        # thum.ioの無料APIでサムネイル画像URLを生成
        # 例: https://image.thum.io/get/https://example.com
        thumb_url = f"https://image.thum.io/get/{url}"
        # サムネイル画像をダウンロード
        try:
            resp = requests.get(thumb_url, timeout=10)
            resp.raise_for_status()
            img_bytes = io.BytesIO(resp.content)
            img_bytes.seek(0)
            file = discord.File(img_bytes, filename="thumbnail.png")
            await interaction.response.send_message(
                content=f"**プレビュー：**\n{url}",
                file=file,
                ephemeral=False
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ プレビュー画像の取得に失敗しました: {e}", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"❌ プレビュー画像の取得に失敗しました: {e}", ephemeral=True)

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
