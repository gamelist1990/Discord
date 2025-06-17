from typing import Optional, Callable, Awaitable
from discord.ext.commands import Bot, Command
import discord
from index import registerSlashCommand as _registerSlashCommand

def register_command(
    bot: Bot,
    command: Command,
    aliases: Optional[list[str]] = None,
    admin: bool = False
) -> None:
    """
    外部プラグイン/モジュールからも呼び出せるようにグローバルに公開。
    command: discord.ext.commands.Command オブジェクト
    aliases: list[str] または None
    admin: bool（管理者専用コマンドかどうか）
    """
    bot.add_command(command)
    # alias機能は廃止（何もしない）
    setattr(command, "admin", admin)


registerSlashCommand = _registerSlashCommand
