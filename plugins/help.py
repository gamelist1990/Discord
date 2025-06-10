from discord.ext import commands
from index import register_command

def setup(bot):
    @commands.command()
    async def help(ctx):
        """
        利用可能なコマンド一覧を見やすくリスト表示します。
        """
        cmds = [f"- `{ctx.prefix}{c.name}`: {c.help or '説明なし'}" for c in bot.commands]
        msg = '【利用可能なコマンド一覧】\n' + '\n'.join(cmds)
        await ctx.send(msg)
    register_command(bot, help, aliases=['h'], admin=False)
