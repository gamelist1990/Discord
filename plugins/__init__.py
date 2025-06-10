def register_command(bot, command, aliases=None, admin=False):
    """
    外部プラグイン/モジュールからも呼び出せるようにグローバルに公開。
    command: discord.ext.commands.Command オブジェクト
    aliases: list[str] または None
    admin: bool（管理者専用コマンドかどうか）
    """
    bot.add_command(command)
    # alias機能は廃止（何もしない）
    setattr(command, "admin", admin)
