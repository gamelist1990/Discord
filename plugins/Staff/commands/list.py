from discord.ext import commands
import discord
from plugins.Staff.util import StaffUtil

@commands.command(name="list")
async def list_cmd(ctx):
    util = StaffUtil(ctx)
    role = util.get_staff_role()
    embed = discord.Embed(title="👥 スタッフ一覧", color=0x2ECC71)
    if not role:
        if await util.is_admin_user():
            embed.description = "現在スタッフはいません"
            embed.set_footer(text="スタッフロールが設定されていません")
            await ctx.send(embed=embed)
            return
        else:
            await ctx.send("スタッフロールを持つメンバーはいません。")
            return
    staff_members = [m for m in ctx.guild.members if role in m.roles and not m.bot]
    if not staff_members:
        embed.description = "現在スタッフはいません"
        await ctx.send(embed=embed)
        return
    staff_names = [
        f"{StaffUtil.get_status_emoji(getattr(m, 'status', None))} {m.display_name}"
        for m in staff_members
    ]
    embed.description = "\n".join(staff_names)
    embed.set_footer(
        text=f"スタッフロール: {role.name} • 合計: {len(staff_members)}名"
    )
    await ctx.send(embed=embed)
