from discord.ext import commands
from plugins import register_command
from index import load_config
from secrets import token_urlsafe
from datetime import datetime, timedelta
from DataBase import save_api_key, get_api_key, delete_api_key
import discord
from discord.ui import View
from plugins.common_ui import ModalInputView

# 一時APIキー発行コマンド

# 一時APIキーのメモリ保存用
issued_api_keys = {}

def setup(bot):
    @commands.command()
    async def auth(ctx, subcmd=None):
        """
        #auth         ...このコマンドの使い方を表示
        #auth gen    ...APIキー発行（その場で表示）
        #auth check  ...フォームでAPIキー有効性チェック
        #auth <key>  ...（従来通り直接チェックも可）
        """
        config = load_config()
        user_id = str(ctx.author.id)
        guild_id = str(ctx.guild.id) if ctx.guild else None
        is_global_admin = user_id in config.get('globalAdmins', [])
        is_guild_admin = guild_id and user_id in config.get('guildAdmins', {}).get(guild_id, [])
        if subcmd is None:
            usage = (
                "【authコマンドの使い方】\n"
                "・#auth gen → 一時APIキーを発行（10分有効、その場で表示）\n"
                "・#auth check → APIキーの有効性をフォームでチェック\n"
                "・#auth <APIキー> → 直接APIキーを検証\n"
                "※APIキー発行は管理者のみ利用可能"
            )
            await ctx.send(usage)
            return
        elif subcmd == "gen":
            # 発行（ボタン→インタラクションでAPIキーをephemeral返却）
            if not (is_global_admin or is_guild_admin):
                await ctx.send('❌ あなたは管理者権限を持っていません。')
                return
            api_key_val = f"API-{token_urlsafe(32)}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            expire = datetime.now() + timedelta(minutes=10)
            save_api_key(user_id, api_key_val, expire)

            async def on_button(interaction: discord.Interaction, view: View):
                # ボタン押下時にAPIキーをephemeralで返す
                await interaction.response.send_message(
                    f"✅ 一時APIキー（10分有効）\n```{api_key_val}```",
                    ephemeral=True
                )

            view = ModalInputView(
                label="APIキーを受け取る",
                on_button=on_button,
                button_emoji="🔑",
                style=discord.ButtonStyle.success,
                auto_delete_on_button=True,
                allowed_user_id=ctx.author.id
            )
            await ctx.send(
                "下のボタンを押すと一時APIキーがあなたにだけ表示されます。",
                view=view
            )
            return
        elif subcmd == "check":
            async def on_api_key_submit(interaction, value, recipient, view):
                key = value.strip()
                info = get_api_key(key)
                if not info:
                    await interaction.response.send_message("❌ 無効なAPIキーです。", ephemeral=True)
                    return
                now = datetime.now()
                if now > info["expire"]:
                    delete_api_key(key)
                    await interaction.response.send_message("⏰ このAPIキーは期限切れです。新しく発行してください。", ephemeral=True)
                else:
                    left = info["expire"] - now
                    await interaction.response.send_message(f"✅ 有効なAPIキーです。\n残り: {left.seconds//60}分{left.seconds%60}秒", ephemeral=True)

            view = ModalInputView(
                modal_title="APIキー入力フォーム",
                label="APIキーを入力",
                placeholder="API-...",
                on_submit=on_api_key_submit,
                text_label="APIキーを入力",
                style=discord.ButtonStyle.primary,
                ephemeral=True,
                max_length=80,
                recipient=ctx.author
            )
            await ctx.send(
                "APIキーの有効性をフォームでチェックできます。下のボタンを押してください。",
                view=view
            )
            return
        else:
            # 直接APIキーを指定してチェック
            key = subcmd.strip()
            info = get_api_key(key)
            if not info:
                await ctx.send("❌ 無効なAPIキーです。")
                return
            now = datetime.now()
            if now > info["expire"]:
                delete_api_key(key)
                await ctx.send("⏰ このAPIキーは期限切れです。新しく発行してください。")
            else:
                left = info["expire"] - now
                await ctx.send(f"✅ 有効なAPIキーです。\n残り: {left.seconds//60}分{left.seconds%60}秒")
    register_command(bot, auth, aliases=None, admin=True)
