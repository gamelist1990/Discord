from discord.ext import commands
import discord

@commands.command(name="help")
async def help_cmd(ctx):
    embed = discord.Embed(
        title="📋 スタッフコマンド一覧",
        description="スタッフ管理用コマンドの使い方",
        color=0x3498DB,
    )
    embed.add_field(
        name="🔍 一般コマンド",
        value="""```
#staff help - このヘルプを表示
#staff list - スタッフ一覧を表示
```""",
        inline=False,
    )
    embed.add_field(
        name="⚙️ 管理コマンド（管理者専用）",
        value="""```
#staff role <roleID> - スタッフロールを設定
#staff alert <チャンネルID|none> - スタッフ通知チャンネルを設定/解除
#staff private - スタッフ専用カテゴリとチャンネルを作成
```""",
        inline=False,
    )
    embed.add_field(
        name="🛡️ 操作コマンド（スタッフのみ）",
        value="""```
#staff timeout @ユーザー <秒数> [理由] - スタッフ以外のユーザーにタイムアウトを付与
#staff kick @ユーザー <理由> - スタッフまたは管理者が実行可能。スタッフ投票で過半数賛成でユーザーをキック
```""",
        inline=False,
    )
    embed.set_footer(text="詳細は各コマンドのヘルプを参照してください。")
    await ctx.send(embed=embed)
