from typing import Optional, Union
import index  # is_adminを利用
import discord
from discord.ext import commands
import re

class SlowmodePlugin:
    """
    Slowmodeプラグイン - チャンネルのslowmode設定を簡単に管理
    
    使用例:
    #slowmode 1s    - 1秒のslowmode
    #slowmode 30s   - 30秒のslowmode
    #slowmode 1m    - 1分のslowmode
    #slowmode 5m    - 5分のslowmode
    #slowmode 1h    - 1時間のslowmode
    #slowmode off   - slowmode解除
    #slowmode       - 現在のslowmode確認
    """

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def parse_time_duration(duration_str: str) -> Optional[int]:
        """
        時間文字列を秒数に変換する
        
        Args:
            duration_str: "1s", "30s", "1m", "5m", "1h", "2h" などの時間文字列
            
        Returns:
            int: 秒数 (0-21600の範囲内)
            None: 無効な形式の場合
        """
        if not duration_str:
            return None
            
        duration_str = duration_str.lower().strip()
        
        # "off", "0", "disable" などはslowmode解除
        if duration_str in ["off", "0", "disable", "disabled", "none", "reset"]:
            return 0
            
        # 正規表現で数値と単位を抽出
        match = re.match(r'^(\d+(?:\.\d+)?)\s*([smh]?)$', duration_str)
        if not match:
            return None
            
        value_str, unit = match.groups()
        
        try:
            value = float(value_str)
        except ValueError:
            return None
            
        # 単位に応じて秒数に変換
        if unit == 's' or unit == '':  # 秒 (単位省略時は秒とみなす)
            seconds = int(value)
        elif unit == 'm':  # 分
            seconds = int(value * 60)
        elif unit == 'h':  # 時間
            seconds = int(value * 3600)
        else:
            return None
            
        # Discordのslowmode制限: 0-21600秒 (0秒-6時間)
        if seconds < 0 or seconds > 21600:
            return None
            
        return seconds

    @staticmethod
    def format_duration(seconds: int) -> str:
        """
        秒数を読みやすい時間文字列に変換
        
        Args:
            seconds: 秒数
            
        Returns:
            str: "30秒", "1分", "1時間30分" などの形式
        """
        if seconds == 0:
            return "無効 (slowmode解除)"
            
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours}時間")
        if minutes > 0:
            parts.append(f"{minutes}分")
        if secs > 0:
            parts.append(f"{secs}秒")
            
        return "".join(parts) if parts else "0秒"

    async def handle_slowmode_command(self, message_or_ctx: Union[discord.Message, commands.Context]):
        # reply_funcを常に初期化（安全なダミー関数）
        async def dummy_reply_func(*args, **kwargs):
            pass
        reply_func = dummy_reply_func
        try:
            # Context/Message両対応でauthor, channel, guild, contentを抽出
            if isinstance(message_or_ctx, commands.Context):
                ctx = message_or_ctx
                author = getattr(ctx, 'author', None)
                channel = getattr(ctx, 'channel', None)
                guild = getattr(ctx, 'guild', None)
                content = ctx.message.content if hasattr(ctx, 'message') else ''
                reply_func = ctx.reply if hasattr(ctx, 'reply') else (ctx.send if hasattr(ctx, 'send') else dummy_reply_func)
            elif isinstance(message_or_ctx, discord.Message):
                msg = message_or_ctx
                author = getattr(msg, 'author', None)
                channel = getattr(msg, 'channel', None)
                guild = getattr(msg, 'guild', None)
                content = msg.content
                reply_func = msg.reply if hasattr(msg, 'reply') else dummy_reply_func
            else:
                return
            # テキストチャンネル以外は拒否
            if not isinstance(channel, discord.TextChannel):
                embed = discord.Embed(
                    title="❌ 無効なチャンネル",
                    description="このコマンドはサーバー内のテキストチャンネルでのみ使用できます。",
                    color=0xFF0000
                )
                await reply_func(embed=embed)
                return
            # author, guild, idのNone安全化
            if not author or not guild or getattr(author, 'id', None) is None or getattr(guild, 'id', None) is None:
                embed = discord.Embed(
                    title="❌ 実行エラー",
                    description="ユーザーまたはサーバー情報が取得できません。再度お試しください。",
                    color=0xFF0000
                )
                await reply_func(embed=embed)
                return
            # 管理者認証: index.is_admin
            from index import load_config, is_admin
            config = load_config()
            if not is_admin(str(author.id), str(guild.id), config):
                embed = discord.Embed(
                    title="❌ 権限不足",
                    description="このコマンドを実行するには管理者権限が必要です。",
                    color=0xFF0000
                )
                await reply_func(embed=embed)
                return
            # コマンド引数取得
            args = content.strip().split()[1:] if content else []
            # 引数なし - 現在のslowmode確認
            if not args:
                current_slowmode = getattr(channel, 'slowmode_delay', 0)
                embed = discord.Embed(
                    title="⏱️ 現在のSlowmode設定",
                    color=0x00FF00
                )
                embed.add_field(
                    name="チャンネル",
                    value=f"{channel.mention}",
                    inline=False
                )
                embed.add_field(
                    name="現在の設定",
                    value=f"{self.format_duration(current_slowmode)}",
                    inline=False
                )
                embed.set_footer(text=f"実行者: {author.display_name}")
                await reply_func(embed=embed)
                return
            # 引数あり - slowmode設定
            duration_str = args[0]
            seconds = self.parse_time_duration(duration_str)
            if seconds is None:
                embed = discord.Embed(
                    title="❌ 無効な時間形式",
                    description=(
                        "有効な時間形式で指定してください。\n\n"
                        "**使用例:**\n"
                        "• `#slowmode 30s` - 30秒\n"
                        "• `#slowmode 1m` - 1分\n"
                        "• `#slowmode 2h` - 2時間\n"
                        "• `#slowmode off` - slowmode解除\n\n"
                        "**制限:** 0秒～6時間まで"
                    ),
                    color=0xFF0000
                )
                await reply_func(embed=embed)
                return
            old_slowmode = getattr(channel, 'slowmode_delay', 0)
            try:
                await channel.edit(
                    slowmode_delay=seconds,
                    reason=f"Slowmode設定変更 by {author} ({author.id})"
                )
                embed = discord.Embed(
                    title="✅ Slowmode設定完了",
                    color=0x00FF00
                )
                embed.add_field(
                    name="チャンネル",
                    value=f"{channel.mention}",
                    inline=False
                )
                embed.add_field(
                    name="変更前",
                    value=f"{self.format_duration(old_slowmode)}",
                    inline=True
                )
                embed.add_field(
                    name="変更後",
                    value=f"{self.format_duration(seconds)}",
                    inline=True
                )
                if seconds == 0:
                    embed.add_field(
                        name="📌 注意",
                        value="Slowmodeが解除されました。",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="📌 注意",
                        value=f"ユーザーは{self.format_duration(seconds)}に1回のみメッセージを送信できます。",
                        inline=False
                    )
                embed.set_footer(text=f"実行者: {author.display_name}")
                await reply_func(embed=embed)
                print(f"[SLOWMODE] {author} ({author.id}) changed slowmode in #{channel.name} from {old_slowmode}s to {seconds}s")
            except discord.errors.Forbidden:
                embed = discord.Embed(
                    title="❌ 権限不足",
                    description="Botにチャンネル編集権限がありません。",
                    color=0xFF0000
                )
                await reply_func(embed=embed)
            except discord.errors.HTTPException as e:
                embed = discord.Embed(
                    title="❌ エラー",
                    description=f"Slowmode設定中にエラーが発生しました: {str(e)}",
                    color=0xFF0000
                )
                await reply_func(embed=embed)
        except Exception as e:
            print(f"[ERROR] Slowmode command error: {e}")
            embed = discord.Embed(
                title="❌ 予期しないエラー",
                description="コマンド実行中に予期しないエラーが発生しました。",
                color=0xFF0000
            )
            try:
                if 'reply_func' in locals():
                    await reply_func(embed=embed)
            except:
                pass

# プラグインの初期化とコマンド登録
def setup(bot):
    """プラグインの初期化"""
    slowmode_plugin = SlowmodePlugin(bot)
      # discord.pyのcommandとして登録
    @bot.command(name='slowmode', help='チャンネルのslowmode設定を管理します')
    async def slowmode_command(ctx, *, duration: str = ""):
        """
        Slowmodeコマンド - discord.pyのコマンドシステム経由
        """
        # コマンド内容を再構築（既存の関数との互換性のため）
        if duration:
            ctx.message.content = f"#slowmode {duration}"
        else:
            ctx.message.content = "#slowmode"
        
        await slowmode_plugin.handle_slowmode_command(ctx.message)
    

# 互換性のため
slowmode_plugin_instance = None

def initialize_slowmode_plugin(bot):
    """既存のプラグインシステムとの互換性のための初期化関数"""
    global slowmode_plugin_instance
    slowmode_plugin_instance = SlowmodePlugin(bot)
    return slowmode_plugin_instance
