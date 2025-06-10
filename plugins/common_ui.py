import discord
from discord.ui import View, Button, Modal, TextInput
from typing import Callable, Optional, Union
import inspect

class ModalInputView(View):
    """
    ボタンを押すとモーダルまたはボタンインタラクションで値を返す汎用View。

    必須:
      - label: ボタンのラベル
      - on_button: ボタン押下時のコールバック (interaction, view) -> awaitable
      - on_submit: モーダル送信時のコールバック (interaction, value, recipient, view) -> awaitable

    オプション:
      - modal_title: モーダルのタイトル
      - placeholder: 入力欄のプレースホルダー
      - text_label: 入力欄のラベル
      - style: discord.ButtonStyle
      - ephemeral: 結果をephemeralで返すか
      - input_style: discord.TextStyle または str（"short"/"long"/"singleline"/"multiline"/"paragraph"）
      - min_length, max_length: 入力長さ制限
      - recipient: メッセージを送る相手（discord.User/discord.Member/None）
      - after_submit: モーダル送信後の追加処理 (interaction, value, recipient, view) -> awaitable
      - button_emoji: ボタンにemojiを付与
      - button_disabled: ボタンを最初から無効化
      - auto_delete_on_button: ボタン押下時にインタラクションメッセージを自動削除する
      - allowed_user_id: ボタンを押せるユーザーID（指定時はそのユーザーのみ）
      - on_button_embed: ボタン押下時に返すEmbed (Callable or Embed or None)
      - on_submit_embed: モーダル送信時に返すEmbed (Callable or Embed or None)
    """
    def __init__(self,
                 label: str,
                 *,
                 on_button: Optional[Callable] = None,
                 on_submit: Optional[Callable] = None,
                 modal_title: str = "入力フォーム",
                 placeholder: str = "ここに入力...",
                 text_label: str = "入力",
                 style: discord.ButtonStyle = discord.ButtonStyle.primary,
                 ephemeral: bool = True,
                 input_style: str = "short",
                 min_length: int = 1,
                 max_length: int = 80,
                 recipient: Optional[Union[discord.User, discord.Member]] = None,
                 after_submit: Optional[Callable] = None,
                 button_emoji: Optional[str] = None,
                 button_disabled: bool = False,
                 auto_delete_on_button: bool = False,
                 allowed_user_id: Optional[int] = None,
                 on_button_embed: Optional[Union[discord.Embed, Callable]] = None,
                 on_submit_embed: Optional[Union[discord.Embed, Callable]] = None):
        super().__init__(timeout=60)
        self.add_item(self.ModalButton(self, label, style, button_emoji, button_disabled))
        self.modal_title = modal_title
        self.placeholder = placeholder
        self.text_label = text_label
        self.on_submit = on_submit
        self.ephemeral = ephemeral
        self.input_style = input_style
        self.min_length = min_length
        self.max_length = max_length
        self.recipient = recipient
        self.on_button = on_button
        self.after_submit = after_submit
        self.auto_delete_on_button = auto_delete_on_button
        self.allowed_user_id = allowed_user_id
        self.on_button_embed = on_button_embed
        self.on_submit_embed = on_submit_embed

    def _resolve_text_style(self):
        # discord.TextStyle/discord.InputTextStyleのバリエーション対応
        style_map = {
            "short": discord.TextStyle.short,
            "singleline": discord.TextStyle.short,
            "long": discord.TextStyle.paragraph,
            "multiline": discord.TextStyle.paragraph,
            "paragraph": discord.TextStyle.paragraph
        }
        if isinstance(self.input_style, str):
            return style_map.get(self.input_style.lower(), discord.TextStyle.short)
        return self.input_style

    class ModalButton(Button):
        def __init__(self, parent, label, style, emoji, disabled):
            super().__init__(label=label, style=style, emoji=emoji, disabled=disabled)
            self.parent = parent
        async def callback(self, interaction: discord.Interaction):
            if self.parent.allowed_user_id is not None and interaction.user.id != self.parent.allowed_user_id:
                await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
                return
            # Embed返却対応
            if self.parent.on_button_embed:
                embed = self.parent.on_button_embed
                if callable(embed):
                    embed = embed(interaction, self.parent)
                    if inspect.isawaitable(embed):
                        embed = await embed
                if isinstance(embed, discord.Embed):
                    await interaction.response.send_message(embed=embed, ephemeral=self.parent.ephemeral)
                else:
                    await interaction.response.send_message(content=str(embed), ephemeral=self.parent.ephemeral)
                if self.parent.auto_delete_on_button:
                    msg = getattr(interaction, "message", None)
                    if msg:
                        try:
                            await msg.delete()
                        except Exception:
                            pass
                return
            if self.parent.on_button:
                await self.parent.on_button(interaction, self.parent)
            if self.parent.auto_delete_on_button:
                msg = getattr(interaction, "message", None)
                if msg:
                    try:
                        await msg.delete()
                    except Exception:
                        pass
                return
            else:
                modal = self.parent.InputModal(self.parent, interaction)
                await interaction.response.send_modal(modal)

    class InputModal(Modal):
        def __init__(self, parent, interaction):
            super().__init__(title=parent.modal_title)
            self.parent = parent
            self.interaction = interaction
            self.input = TextInput(
                label=parent.text_label,
                placeholder=parent.placeholder,
                required=True,
                style=parent._resolve_text_style(),
                min_length=parent.min_length,
                max_length=parent.max_length
            )
            self.add_item(self.input)
        async def on_submit(self, interaction: discord.Interaction):
            recipient = self.parent.recipient
            if recipient is None:
                recipient = getattr(self.parent, 'recipient', None)
                if recipient is None:
                    recipient = interaction.user
            # Embed返却対応
            if self.parent.on_submit_embed:
                embed = self.parent.on_submit_embed
                if callable(embed):
                    embed = embed(interaction, self.input.value, recipient, self.parent)
                    if inspect.isawaitable(embed):
                        embed = await embed
                if isinstance(embed, discord.Embed):
                    await interaction.response.send_message(embed=embed, ephemeral=self.parent.ephemeral)
                else:
                    await interaction.response.send_message(content=str(embed), ephemeral=self.parent.ephemeral)
            elif self.parent.on_submit:
                await self.parent.on_submit(interaction, self.input.value, recipient, self.parent)
            else:
                await interaction.response.send_message(f"入力値: {self.input.value}", ephemeral=self.parent.ephemeral)
            if self.parent.after_submit:
                await self.parent.after_submit(interaction, self.input.value, recipient, self.parent)
