from discord.ext import commands
import discord
from plugins.Staff.util import StaffUtil
from DataBase import update_guild_data

@commands.command(name="role")
async def role_cmd(ctx, role_id: int):
    util = StaffUtil(ctx)
    if not (await util.is_admin_user()):
        await ctx.send("このコマンドは管理者専用です。"); return
    role = discord.utils.get(ctx.guild.roles, id=role_id)
    if not role:
        await ctx.send("指定したロールIDのロールが見つかりません。"); return
    update_guild_data(ctx.guild.id, "staffRole", str(role_id))
    await ctx.send(f"スタッフロールを {role.mention} に設定しました。")
