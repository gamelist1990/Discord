import discord
from discord import app_commands
from discord.ext import commands
from utils import load_config_file

CONFIG_FILE_NAME = "config.json"
ECO_MODE_STATE = {"enabled": False}

def is_global_admin(user_id):
    config = load_config_file(CONFIG_FILE_NAME)
    return str(user_id) in config.get("globalAdmins", [])

class Eco(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="eco", description="エコモードのON/OFF (グローバル管理者専用)")
    @app_commands.describe(enable="trueでON, falseでOFF")
    async def eco(self, interaction: discord.Interaction, enable: bool):
        if not is_global_admin(interaction.user.id):
            await interaction.response.send_message("グローバル管理者のみ実行可能です。", ephemeral=True)
            return
        ECO_MODE_STATE["enabled"] = enable
        await interaction.response.send_message(f"エコモードを{'有効' if enable else '無効'}にしました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        if ECO_MODE_STATE["enabled"]:
            # miniAntiとスラッシュコマンド以外は無効化
            if ctx.command and ctx.command.name != "miniAnti" and not ctx.interaction:
                raise commands.CheckFailure("Eco mode: command blocked.")

async def setup(bot):
    await bot.add_cog(Eco(bot))
