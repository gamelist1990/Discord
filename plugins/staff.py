from discord.ext import commands
from plugins import register_command
from lib.op import OP_STAFF
from plugins.Staff.commands.timeout import timeout_cmd
from plugins.Staff.commands.kick import kick_cmd
from plugins.Staff.commands.role import role_cmd
from plugins.Staff.commands.alert import alert_cmd
from plugins.Staff.commands.help import help_cmd
from plugins.Staff.commands.list import list_cmd
from plugins.Staff.commands.private import private_cmd
from plugins.Staff.commands.report import report_cmd
from plugins.Staff.commands.privateChat import setup as private_chat_setup


def setup(bot):
    @commands.group()
    async def staff(ctx):
        pass

    staff.add_command(timeout_cmd)
    staff.add_command(kick_cmd)
    staff.add_command(role_cmd)
    staff.add_command(alert_cmd)
    staff.add_command(help_cmd)
    staff.add_command(list_cmd)
    staff.add_command(private_cmd)
    staff.add_command(private_chat_setup())
    staff.add_command(report_cmd)

    register_command(bot, staff, op_level=OP_STAFF)
