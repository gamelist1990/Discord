from discord.ext import commands
from plugins import register_command
from plugins.Staff.commands import (
    timeout_cmd,
    kick_cmd,
    role_cmd,
    alert_cmd,
    help_cmd,
    list_cmd,
    private_cmd,
    report_cmd,
)


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
    staff.add_command(report_cmd)

    register_command(bot, staff)
