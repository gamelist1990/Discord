from typing import Callable, Awaitable
from discord.ext.commands import Bot, Command, Context
import discord
from index import registerSlashCommand as _registerSlashCommand
from lib.op import has_op, OP_EVERYONE, OP_HAS_ROLE, OP_STAFF, OP_GUILD_ADMIN, OP_GLOBAL_ADMIN

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
        if not isinstance(member, discord.Member):
            await ctx.send("❌ このコマンドはサーバー内でのみ使用できます。")
            return
        if not has_op(member, op_level):
            await ctx.send("❌ 権限がありません。")
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
        if member and not has_op(member, op_level):
            return interaction.response.send_message("❌ 権限がありません。", ephemeral=True)
        return callback(interaction, *args, **kwargs)
    return _registerSlashCommand(bot, name, description, wrapped_callback, parameters)