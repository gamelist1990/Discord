from discord.ext import commands
import discord
from plugins.Staff.util import StaffUtil
from DataBase import update_guild_data

@commands.command(name="alert")
async def alert_cmd(ctx, channel_id_or_none: str):
    util = StaffUtil(ctx)
    if not (await util.is_admin_user()):
        await ctx.send("このコマンドは管理者専用です。"); return
    if channel_id_or_none.lower() == "none":
        update_guild_data(ctx.guild.id, "alertChannel", None)
        await ctx.send("通知チャンネル設定を解除しました。"); return
    try:
        channel_id = int(channel_id_or_none)
        channel = ctx.guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            await ctx.send("指定したチャンネルIDのテキストチャンネルが見つかりません。"); return
        update_guild_data(ctx.guild.id, "alertChannel", str(channel_id))
        await ctx.send(f"通知チャンネルを {channel.mention} に設定しました。")
    except Exception:
        await ctx.send("チャンネルIDが不正です。")
