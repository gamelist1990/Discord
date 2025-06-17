import discord
from plugins import registerSlashCommand


def setup(bot):
    async def ping_callback(interaction: discord.Interaction):
        latency = bot.latency * 1000 # ms
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Botの応答速度: `{latency:.2f}ms`",
            color=0x2ecc71
        )
        embed.set_footer(text=f"サーバー: {interaction.guild.name if interaction.guild else 'DM'} | 実行者: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    registerSlashCommand(bot, "ping", "Botの応答速度を表示します。", ping_callback)

   
