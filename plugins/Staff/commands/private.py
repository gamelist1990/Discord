from discord.ext import commands
import discord
from plugins.Staff.util import StaffUtil

@commands.command(name="private")
async def private_cmd(ctx):
    util = StaffUtil(ctx)
    if not (await util.is_admin_user()):
        await ctx.send("このコマンドは管理者専用です。"); return
    guild = ctx.guild
    category_name = "🛡️スタッフ専用"
    channel_name = "staff-chat"
    category = discord.utils.get(guild.categories, name=category_name)
    role = util.get_staff_role()
    if not role:
        await ctx.send("スタッフロールが設定されていません。"); return
    if not category:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            role: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        category = await guild.create_category(category_name, overwrites=overwrites)
        await ctx.send(f"カテゴリ {category_name} を作成しました。")
    else:
        await ctx.send(f"カテゴリ {category_name} は既に存在します。")
    channel = (
        discord.utils.get(category.text_channels, name=channel_name)
        if category
        else None
    )
    if not channel:
        channel = await guild.create_text_channel(channel_name, category=category)
        await ctx.send(f"チャンネル {channel.mention} を作成しました。")
    else:
        await ctx.send(f"チャンネル {channel.mention} は既に存在します。")
