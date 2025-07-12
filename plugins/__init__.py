from typing import Callable, Awaitable
from discord.ext.commands import Bot, Command, Context
import discord
from index import registerSlashCommand as _registerSlashCommand
from lib.op import has_op, OP_EVERYONE, OP_HAS_ROLE, OP_STAFF, OP_GUILD_ADMIN, OP_GLOBAL_ADMIN
import time

# ユーザーごとの直近エラー通知履歴（(user_id, command, error_type): timestamp）
_error_notify_history = {}
_ERROR_NOTIFY_WINDOW = 5  # 秒

def register_command(
    bot: Bot,
    command: Command,
    op_level: int = OP_EVERYONE
) -> None:
    """
    外部プラグイン/モジュールからも呼び出せるようにグローバルに公開。
    command: discord.ext.commands.Command オブジェクト
    op_level: 必要なopレベル（0=全員, 1=ロール, 2=Staff, 3=ギルド管理者, 4=グローバル管理者）
    """
    original_callback = command.callback
    async def wrapped_callback(*args, **kwargs):
        # ctxは関数型ならargs[0]、メソッド型ならargs[1]
        if len(args) == 0:
            raise RuntimeError("コマンドコールバックにctxが渡されていません")
        ctx = args[0] if isinstance(args[0], Context) else args[1] if len(args) > 1 and isinstance(args[1], Context) else None
        if ctx is None:
            raise RuntimeError("ctxが見つかりません")
        member = ctx.author
        user_id = str(member.id) if hasattr(member, 'id') else None
        # コマンド名取得の安全化
        if hasattr(ctx, 'command') and ctx.command is not None:
            cmd_name = getattr(ctx.command, 'qualified_name', None) or getattr(ctx.command, 'name', None) or str(ctx.command)
        else:
            cmd_name = None
        now = time.time()
        # サーバー外
        if not isinstance(member, discord.Member):
            key = (user_id, cmd_name, 'guild_only')
            last = _error_notify_history.get(key, 0)
            if now - last > _ERROR_NOTIFY_WINDOW:
                # なにもしない 
                _error_notify_history[key] = now
            return
        # 権限不足
        if not has_op(member, op_level):
            key = (user_id, cmd_name, 'no_permission')
            last = _error_notify_history.get(key, 0)
            if now - last > _ERROR_NOTIFY_WINDOW:
                await ctx.send("❌ 権限がありません。")
                _error_notify_history[key] = now
            return
        await original_callback(*args, **kwargs)

    command.callback = wrapped_callback
    bot.add_command(command)
    setattr(command, "op_level", op_level)


def registerSlashCommand(bot, name, description, callback, parameters=None, op_level=OP_EVERYONE):
    """
    スラッシュコマンドを動的に登録する関数。
    op_level: 必要なopレベル（0=全員, 1=ロール, 2=Staff, 3=ギルド管理者, 4=グローバル管理者）
    """
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
            return  # スルー
        return callback(interaction, *args, **kwargs)
    return _registerSlashCommand(bot, name, description, wrapped_callback, parameters)