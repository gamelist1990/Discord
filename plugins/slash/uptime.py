import discord
from plugins import registerSlashCommand
from lib.op import OP_EVERYONE
import utils
from datetime import datetime

def setup(bot):
    async def uptime_callback(interaction: discord.Interaction):
        bot_start_time = utils.get_bot_start_time()
        if bot_start_time is None:
            await interaction.response.send_message("起動時刻が取得できませんでした。", ephemeral=True)
            return
        
        # 稼働時間の計算
        current_time = datetime.now()
        uptime_delta = current_time - bot_start_time
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Discordタイムスタンプを生成
        start_timestamp = int(bot_start_time.timestamp())
        relative_timestamp = f"<t:{start_timestamp}:R>"  # 相対時間（例：2時間前）
        absolute_timestamp = f"<t:{start_timestamp}:F>"  # 絶対時間（例：2024年1月1日 12:00）
        
        # ステータスの決定
        if days >= 30:
            icon = "🌟"
            color = 0x00ff00
            status_text = "長期安定稼働中"
        elif days >= 7:
            icon = "💪"
            color = 0x3498db
            status_text = "安定稼働中"
        elif days >= 1:
            icon = "⚡"
            color = 0xf39c12
            status_text = "順調稼働中"
        else:
            icon = "🚀"
            color = 0xe74c3c
            status_text = "起動直後"
        
        # 稼働時間のフォーマット
        if days > 0:
            uptime_display = f"{days}日 {hours}時間 {minutes}分"
        elif hours > 0:
            uptime_display = f"{hours}時間 {minutes}分 {seconds}秒"
        else:
            uptime_display = f"{minutes}分 {seconds}秒"
        
        # Embedの作成（スマホ・PC対応のレイアウト）
        embed = discord.Embed(
            title=f"{icon} Bot稼働時間",
            description=f"**{status_text}**",
            color=color
        )
        
        # フィールドを縦並びで統一（スマホでも見やすい）
        embed.add_field(
            name="⏱️ 稼働時間",
            value=f"```\n{uptime_display}\n```",
            inline=False
        )
        
        embed.add_field(
            name="⏰ 起動時刻",
            value=f"{absolute_timestamp}\n{relative_timestamp}",
            inline=False
        )
        
        embed.add_field(
            name="📊 ステータス情報",
            value=f"🟢 **オンライン** • 正常稼働中\n📈 **稼働日数:** {days}日間",
            inline=False
        )
        
        embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/852881844519706634.gif?size=64")
        embed.set_footer(
            text=f"🤖 {bot.user.name} | 📍 {interaction.guild.name if interaction.guild else 'DM'}",
            icon_url=bot.user.avatar.url if bot.user and bot.user.avatar else None
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    registerSlashCommand(
        bot,
        "uptime",
        "Botの現在の稼働時間を表示します。",
        uptime_callback,
        op_level=OP_EVERYONE
    )
