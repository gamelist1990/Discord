from discord.ext import commands
import discord
from plugins.Staff.util import StaffUtil
from typing import Union

@commands.command(name="kick")
async def kick_cmd(ctx: commands.Context, member_or_id: Union[discord.Member, str], *, reason: str):
    util = StaffUtil(ctx)
    role = util.get_staff_role()
    member = member_or_id
    if ctx.guild is None:
        await ctx.send("このコマンドはギルド内でのみ使用できます。")
        return
    try:
        if isinstance(member_or_id, str) and member_or_id.isdigit():
            member = await ctx.guild.fetch_member(int(member_or_id))
    except discord.NotFound:
        await ctx.send(f"ID: {member_or_id} のユーザーが見つかりません。")
        return
    except discord.HTTPException:
        await ctx.send("ユーザー情報の取得中にエラーが発生しました。")
        return
    if not isinstance(member, discord.Member):
        await ctx.send("指定されたユーザーが無効です。")
        return
    if not role:
        await ctx.send("スタッフロールが設定されていません。"); return
    if role in member.roles:
        await ctx.send("スタッフはキックできません。"); return
    if member.bot:
        await ctx.send("Botはキックできません。"); return
    async def do_kick(ctx, member, reason):
        await member.kick(reason=f"スタッフ投票により可決: {reason}")
    await util.vote_action(ctx, member, "キック", reason, do_kick, timeout_sec=300)
