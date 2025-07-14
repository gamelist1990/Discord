
from typing import Callable, Awaitable
from discord.ext.commands import Bot, Command, Context
import discord
from lib.op import has_op, OP_EVERYONE, OP_STAFF
import time
import asyncio

# スラッシュコマンドのエラー通知履歴と通知間隔（秒）
_error_notify_history = {}
_ERROR_NOTIFY_WINDOW = 10  # 例: 10秒間隔で同じユーザーにエラー通知

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
        if hasattr(command, 'invoke') and callable(command.invoke):
            if inspect.iscoroutinefunction(command.invoke):
                await command.invoke(ctx)
            else:
                command.invoke(ctx)
        else:
            await command(ctx, *args)
    COMMAND_TABLE[name] = (wrapper, op_level, command.help if hasattr(command, "help") else "")

async def handle_custom_command(message:discord.Message):
    if message.author.bot or not message.guild:
        return
    if not message.content.startswith("#"):
        return
    parts = message.content[1:].split()
    cmd = parts[0] if parts else None
    args = parts[1:] if len(parts) > 1 else []
    if cmd in COMMAND_TABLE:
        func, op_level, _ = COMMAND_TABLE[cmd]
        if isinstance(message.author, discord.Member) and has_op(message.author, op_level):
            try:
                res = func(message, args)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                print(f"コマンド実行エラー: {e}")
        else:
            await message.reply("❌ 権限がありません。")


# --- 既存のregister_command等は無効化またはコメントアウト可 ---


def registerSlashCommand(bot, name, description, callback, parameters=None, op_level=OP_EVERYONE):
    """
    スラッシュコマンドを動的に登録する関数。
    op_level: 必要なopレベル（0=全員, 1=ロール, 2=Staff, 3=ギルド管理者, 4=グローバル管理者）
    """
    import typing
    import discord.app_commands as app_commands
    tree = bot.tree if hasattr(bot, 'tree') else None
    if not tree:
        print("❌ スラッシュコマンドツリーが見つかりません")
        return
    import inspect
    def wrapped_callback(interaction, *args, **kwargs):
        member = interaction.user if hasattr(interaction, "user") else None
        user_id = str(member.id) if member and hasattr(member, 'id') else None
        now = time.time()
        key = (user_id, name, 'no_permission')
        if member and not has_op(member, op_level):
            last = _error_notify_history.get(key, 0)
            if now - last > _ERROR_NOTIFY_WINDOW:
                _error_notify_history[key] = now
                return interaction.response.send_message("❌ 権限がありません。", ephemeral=True)
            return None  # スルー
        res = callback(interaction, *args, **kwargs)
        if inspect.isawaitable(res):
            return res
        return None
    # 既存のコマンドがある場合は削除
    try:
        existing_command = tree.get_command(name)
        if existing_command:
            tree.remove_command(name)
    except:
        pass
    if parameters:
        param_count = len(parameters)
        describe_dict = {param["name"]: param.get("description", "") for param in parameters}
        if param_count == 1:
            param = parameters[0]
            param_name = param["name"]
            param_type = param.get("type", str)
            param_required = param.get("required", True)
            if param_type == discord.Member:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_member_required(interaction: discord.Interaction, user: discord.Member):
                        res = wrapped_callback(interaction, user)
                        if res is not None:
                            await res
                    tree.add_command(cmd_member_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_member_optional(interaction: discord.Interaction, user: typing.Optional[discord.Member] = None):
                        res = wrapped_callback(interaction, user)
                        if res is not None:
                            await res
                    tree.add_command(cmd_member_optional)
            elif param_type == str:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_str_required(interaction: discord.Interaction, text: str):
                        res = wrapped_callback(interaction, text)
                        if res is not None:
                            await res
                    tree.add_command(cmd_str_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_str_optional(interaction: discord.Interaction, text: typing.Optional[str] = None):
                        res = wrapped_callback(interaction, text)
                        if res is not None:
                            await res
                    tree.add_command(cmd_str_optional)
            elif param_type == int:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_int_required(interaction: discord.Interaction, number: int):
                        res = wrapped_callback(interaction, number)
                        if res is not None:
                            await res
                    tree.add_command(cmd_int_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_int_optional(interaction: discord.Interaction, number: typing.Optional[int] = None):
                        res = wrapped_callback(interaction, number)
                        if res is not None:
                            await res
                    tree.add_command(cmd_int_optional)
            else:
                @app_commands.command(name=name, description=description)
                @app_commands.describe(**describe_dict)
                async def cmd_other(interaction: discord.Interaction, value: typing.Optional[str] = None):
                    res = wrapped_callback(interaction, value)
                    if res is not None:
                        await res
                tree.add_command(cmd_other)
        elif param_count == 2:
            param1 = parameters[0]
            param2 = parameters[1]
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_two_params(interaction: discord.Interaction, arg1: typing.Any, arg2: typing.Any):
                res = wrapped_callback(interaction, arg1, arg2)
                if res is not None:
                    await res
            tree.add_command(cmd_two_params)
        elif param_count == 3:
            param1 = parameters[0]
            param2 = parameters[1]
            param3 = parameters[2]
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_three_params(interaction: discord.Interaction, arg1: typing.Any, arg2: typing.Any, arg3: typing.Any):
                res = wrapped_callback(interaction, arg1, arg2, arg3)
                if res is not None:
                    await res
            tree.add_command(cmd_three_params)
        else:
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_multi_params(interaction: discord.Interaction):
                res = wrapped_callback(interaction)
                if res is not None:
                    await res
            tree.add_command(cmd_multi_params)
    else:
        @app_commands.command(name=name, description=description)
        async def cmd_no_params(interaction: discord.Interaction):
            res = wrapped_callback(interaction)
            if res is not None:
                await res
        tree.add_command(cmd_no_params)
    print(f"✔ スラッシュコマンド /{name} を登録しました。")