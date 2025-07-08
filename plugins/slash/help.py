import discord
from plugins import registerSlashCommand
from lib.op import OP_EVERYONE


def setup(bot):
    async def help_callback(interaction: discord.Interaction):
        global_cmds = bot.tree.get_commands()
        guild_cmds = bot.tree.get_commands(guild=interaction.guild)
        all_cmds = {cmd.name: cmd for cmd in global_cmds}
        all_cmds.update({cmd.name: cmd for cmd in guild_cmds})
        cmds = list(all_cmds.values())

        # 基本説明文
        base_desc = "利用可能なスラッシュコマンド一覧です。"

        # コマンドがない場合の説明文
        if not cmds:
            base_desc += (
                "\n\n**コマンドが見つかりません。現在利用可能なコマンドはありません。**"
            )

        embed = discord.Embed(
            title="🔍 コマンド一覧",
            description=base_desc,
            color=0x3498db
        )

        if cmds:
            value = ""
            for cmd in sorted(cmds, key=lambda x: x.name):
                value += f"`/{cmd.name}` - {cmd.description}\n"

            embed.add_field(
                name="📌 利用可能なコマンド",
                value=value,
                inline=False
            )

        bot_name = bot.user.name if bot.user else "Bot"
        embed.set_footer(
            text=f"{bot_name} | サーバー: {interaction.guild.name if interaction.guild else 'DM'}"
        )
        if bot.user and bot.user.avatar:
            embed.set_thumbnail(url=bot.user.avatar.url)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    registerSlashCommand(
        bot,
        "help",
        "利用可能なスラッシュコマンド一覧を表示します。",
        help_callback,
        op_level=OP_EVERYONE
    )
