
from typing import Callable, Awaitable
from discord.ext.commands import Bot, Command, Context
from discord import app_commands
import discord
from lib.op import has_op, OP_EVERYONE, OP_STAFF
import time
import asyncio


# スラッシュコマンドのエラー通知履歴と通知間隔（秒）
_error_notify_history = {}
_ERROR_NOTIFY_WINDOW = 10  # 例: 10秒間隔で同じユーザーにエラー通知

# コマンドキャッシュ（RateLimit対策）
_COMMAND_CACHE = {}
_USER_COMMAND_NAMES = set()  # user=Trueで登録されたコマンド名を記録

# --- コマンド登録・実行ラッパー ---
COMMAND_TABLE = {}


def register_command(bot, command, op_level=OP_EVERYONE):
    """
    使い方は従来通り: register_command(bot, command, op_level)
    ただしコマンドはBotにaddせず、COMMAND_TABLEに登録するだけ
    """
    name = command.name if hasattr(command, "name") else str(command)
    import inspect

    async def wrapper(message, args):
        ctx = await bot.get_context(message)
        # discord.pyのGroup/Commandはinvoke(ctx)で正しく動作する
        if hasattr(command, "invoke") and callable(command.invoke):
            if inspect.iscoroutinefunction(command.invoke):
                await command.invoke(ctx)
            else:
                command.invoke(ctx)
        else:
            await command(ctx, *args)

    COMMAND_TABLE[name] = (
        wrapper,
        op_level,
        command.help if hasattr(command, "help") else "",
    )


async def handle_custom_command(message: discord.Message):
    if message.author.bot or not message.guild:
        return
    if not message.content.startswith("#"):
        return
    parts = message.content[1:].split()
    cmd = parts[0] if parts else None
    args = parts[1:] if len(parts) > 1 else []
    if cmd in COMMAND_TABLE:
        func, op_level, _ = COMMAND_TABLE[cmd]
        if isinstance(message.author, discord.Member) and has_op(
            message.author, op_level
        ):
            try:
                res = func(message, args)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"コマンド実行エラー: {e}")
        else:
            await message.reply("❌ 権限がありません。")


# --- 既存のregister_command等は無効化またはコメントアウト可 ---


def registerSlashCommand(
    bot, name, description, callback, parameters=None, op_level=OP_EVERYONE, user=False
):
    """
    スラッシュコマンド・ユーザーコマンドを動的に登録する関数。
    user=True でユーザーコマンド（ContextMenu）として登録、かつ権限チェックを行わない。
    user=False（デフォルト）で通常のスラッシュコマンド。
    op_level: 必要なopレベル（0=全員, 1=ロール, 2=Staff, 3=ギルド管理者, 4=グローバル管理者）
    """
    import typing
    import discord.app_commands as app_commands
    tree = bot.tree if hasattr(bot, "tree") else None
    if not tree:
        print("❌ スラッシュコマンドツリーが見つかりません")
        return
    import inspect

    if user:
        _USER_COMMAND_NAMES.add(name)


    def wrapped_callback(interaction, *args, **kwargs):
        print(f"[DEBUG] wrapped_callback called: name={name}, args={args}, kwargs={kwargs}")
        # user=Trueで登録されたコマンド名なら必ずユーザーコマンド分岐
        if name in _USER_COMMAND_NAMES:
            print(f"[DEBUG] User command (user=True) forced branch for name={name}")
            res = callback(interaction, *args, **kwargs)
            if inspect.isawaitable(res):
                return res
            return None
        # 通常のスラッシュコマンド: guild/権限チェックあり
        member = interaction.user if hasattr(interaction, "user") else None
        print(f"[DEBUG] Slash command detected, member={member}")
        user_id = str(member.id) if member and hasattr(member, "id") else None
        now = time.time()
        key = (user_id, name, "no_permission")
        if member and not isinstance(member, discord.Member):
            print(f"[DEBUG] Not a guild member, aborting with error message.")
            return interaction.response.send_message(
                "❌ このコマンドはサーバー内でのみ利用できます。", ephemeral=True
            )
        if member and not has_op(member, op_level):
            print(f"[DEBUG] Permission denied for user_id={user_id}, op_level={op_level}")
            last = _error_notify_history.get(key, 0)
            if now - last > _ERROR_NOTIFY_WINDOW:
                _error_notify_history[key] = now
                return interaction.response.send_message(
                    "❌ 権限がありません。", ephemeral=True
                )
            print(f"[DEBUG] Permission denied, but error window not elapsed. No response sent.")
            return None  # スルー
        print(f"[DEBUG] Permission OK, calling callback.")
        res = callback(interaction, *args, **kwargs)
        if inspect.isawaitable(res):
            return res
        return None

    def _add_command(cmd):
        tree.add_command(cmd)

    # 既存のコマンドがある場合は削除（キャッシュ利用）
    try:
        cache_key = ("slash", name)
        existing_command = _COMMAND_CACHE.get(cache_key)
        if existing_command is None:
            existing_command = tree.get_command(name)
            _COMMAND_CACHE[cache_key] = existing_command
        if existing_command:
            tree.remove_command(name)
            _COMMAND_CACHE[cache_key] = None
    except Exception as e:
        print(f"(info) 既存スラッシュコマンド削除時の例外: {e}")
    if parameters:
        param_count = len(parameters)
        describe_dict = {
            param["name"]: param.get("description", "") for param in parameters
        }
        if param_count == 1:
            param = parameters[0]
            param_name = param["name"]
            param_type = param.get("type", str)
            param_required = param.get("required", True)
            if param_type == discord.Member:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_member_required(
                        interaction: discord.Interaction, user: discord.Member
                    ):
                        res = wrapped_callback(interaction, user)
                        if res is not None:
                            await res
                    _add_command(cmd_member_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_member_optional(
                        interaction: discord.Interaction,
                        user: typing.Optional[discord.Member] = None,
                    ):
                        res = wrapped_callback(interaction, user)
                        if res is not None:
                            await res
                    _add_command(cmd_member_optional)
            elif param_type == discord.User:
                # ユーザーコマンド用
                @app_commands.context_menu(name=name)
                async def user_context_menu(interaction: discord.Interaction, user: discord.User):
                    res = wrapped_callback(interaction, user)
                    if res is not None:
                        await res
                _add_command(user_context_menu)
            elif param_type == str:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_str_required(
                        interaction: discord.Interaction, text: str
                    ):
                        res = wrapped_callback(interaction, text)
                        if res is not None:
                            await res
                    _add_command(cmd_str_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_str_optional(
                        interaction: discord.Interaction,
                        text: typing.Optional[str] = None,
                    ):
                        res = wrapped_callback(interaction, text)
                        if res is not None:
                            await res
                    _add_command(cmd_str_optional)
            elif param_type == int:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_int_required(
                        interaction: discord.Interaction, number: int
                    ):
                        res = wrapped_callback(interaction, number)
                        if res is not None:
                            await res
                    _add_command(cmd_int_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_int_optional(
                        interaction: discord.Interaction,
                        number: typing.Optional[int] = None,
                    ):
                        res = wrapped_callback(interaction, number)
                        if res is not None:
                            await res
                    _add_command(cmd_int_optional)
            else:
                @app_commands.command(name=name, description=description)
                @app_commands.describe(**describe_dict)
                async def cmd_other(
                    interaction: discord.Interaction, value: typing.Optional[str] = None
                ):
                    res = wrapped_callback(interaction, value)
                    if res is not None:
                        await res
                _add_command(cmd_other)
        elif param_count == 2:
            param1 = parameters[0]
            param2 = parameters[1]
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_two_params(
                interaction: discord.Interaction, arg1: typing.Any, arg2: typing.Any
            ):
                res = wrapped_callback(interaction, arg1, arg2)
                if res is not None:
                    await res
            _add_command(cmd_two_params)
        elif param_count == 3:
            param1 = parameters[0]
            param2 = parameters[1]
            param3 = parameters[2]
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_three_params(
                interaction: discord.Interaction,
                arg1: typing.Any,
                arg2: typing.Any,
                arg3: typing.Any,
            ):
                res = wrapped_callback(interaction, arg1, arg2, arg3)
                if res is not None:
                    await res
            _add_command(cmd_three_params)
        else:
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_multi_params(interaction: discord.Interaction):
                res = wrapped_callback(interaction)
                if res is not None:
                    await res
            _add_command(cmd_multi_params)
    else:
        @app_commands.command(name=name, description=description)
        async def cmd_no_params(interaction: discord.Interaction):
            res = wrapped_callback(interaction)
            if res is not None:
                await res
        _add_command(cmd_no_params)
    print(f"✔ スラッシュコマンド /{name} を登録しました。 (op_level={op_level}, user={user})")





def registerMessageCommand(bot, name, callback, description=None):
    """
    メッセージコンテキストメニューコマンドを動的に登録する関数。
    name: コマンド名
    callback: (interaction, message) -> awaitable
    description: オプション（未使用、将来用）
    """
    import discord
    tree = bot.tree if hasattr(bot, "tree") else None
    if not tree:
        print("❌ スラッシュコマンドツリーが見つかりません")
        return
    # 既存のコマンドがある場合は削除（キャッシュ利用）
    try:
        cache_key = ("message", name)
        existing_command = _COMMAND_CACHE.get(cache_key)
        if existing_command is None:
            existing_command = tree.get_command(name)
            _COMMAND_CACHE[cache_key] = existing_command
        if existing_command:
            tree.remove_command(name)
            _COMMAND_CACHE[cache_key] = None
    except Exception as e:
        print(f"(info) 既存メッセージコマンド削除時の例外: {e}")
    @discord.app_commands.context_menu(name=name)
    async def message_context_menu(interaction: discord.Interaction, message: discord.Message):
        res = callback(interaction, message)
        if hasattr(res, "__await__"):
            await res
    tree.add_command(message_context_menu)
    print(f"✔ メッセージコマンド '{name}' を登録しました。")