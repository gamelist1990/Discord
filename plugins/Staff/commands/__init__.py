# Staffコマンド群の登録用パッケージ

from plugins.Staff.commands.timeout import timeout_cmd
from plugins.Staff.commands.kick import kick_cmd
from plugins.Staff.commands.role import role_cmd
from plugins.Staff.commands.alert import alert_cmd
from plugins.Staff.commands.help import help_cmd
from plugins.Staff.commands.list import list_cmd
from plugins.Staff.commands.private import private_cmd
from plugins.Staff.commands.report import report_cmd

__all__ = [
    "timeout_cmd",
    "kick_cmd",
    "role_cmd",
    "alert_cmd",
    "help_cmd",
    "list_cmd",
    "private_cmd",
    "report_cmd",
]
