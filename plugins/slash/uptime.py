import discord
from plugins import registerSlashCommand
import utils
import sys
from datetime import datetime

# index.py でグローバルな bot_start_time を使うため
if hasattr(sys.modules.get('index'), 'bot_start_time'):
    from index import bot_start_time
else:
    bot_start_time = None

def setup(bot):
    async def uptime_callback(interaction: discord.Interaction):
        # bot_start_time を取得
        global bot_start_time
        if bot_start_time is None:
            # index.py から取得できない場合は起動時刻不明
            await interaction.response.send_message("起動時刻が取得できませんでした。", ephemeral=True)
            return
        uptime_str = utils.format_uptime(bot_start_time)
        start_time_str = bot_start_time.strftime("%Y年%m月%d日 %H:%M:%S")
        
        # 稼働時間に応じてアイコンと色を変更
        uptime_delta = bot_start_time
        days = (datetime.now() - bot_start_time).days
        
        if days >= 30:
            icon = "🌟"
            color = 0x00ff00  # 緑色（長期安定稼働）
            status_text = "長期安定稼働中"
        elif days >= 7:
            icon = "💪"
            color = 0x3498db  # 青色（安定稼働）
            status_text = "安定稼働中"
        elif days >= 1:
            icon = "⚡"
            color = 0xf39c12  # オレンジ色（短期稼働）
            status_text = "順調稼働中"
        else:
            icon = "🚀"
            color = 0xe74c3c  # 赤色（起動直後）
            status_text = "起動直後"
        
        embed = discord.Embed(
            title=f"{icon} Bot稼働時間 (Uptime)",
            description=f"**{status_text}**\n\n📊 **現在の稼働時間:**\n```yaml\n{uptime_str}\n```\n\n🕐 **開始時刻:** {start_time_str}",
            color=color
        )
        
        # 追加情報フィールドを追加
        embed.add_field(
            name="📈 稼働日数",
            value=f"{days}日間",
            inline=True
        )
        
        embed.add_field(
            name="🔄 ステータス",
            value="🟢 オンライン",
            inline=True
        )
        
        embed.add_field(
            name="🏃‍♂️ パフォーマンス",
            value=f"正常動作中",
            inline=True
        )
        
        # サムネイルとフッターを設定
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
        uptime_callback
    )
