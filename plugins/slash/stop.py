import discord
from plugins import registerSlashCommand
from lib.op import *


# グローバル管理者のみが使える stop コマンド

def setup(bot):
    async def stop_callback(interaction: discord.Interaction):
        await interaction.response.send_message("Botを停止します。", ephemeral=True)
        import sys
        import asyncio
        await asyncio.sleep(1)
        sys.exit(0)

    registerSlashCommand(
        bot,
        "stop",
        "Botプロセスを停止します（グローバル管理者専用）",
        stop_callback,
        op_level=OP_GLOBAL_ADMIN,
    )
