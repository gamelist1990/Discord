import sys
import os
import json
import asyncio
import importlib.util
import glob
from discord.ext import commands, tasks
from discord import Embed
from datetime import datetime, timedelta
from plugins import register_command

# 新しいLotteryDatabaseをインポート
try:
    from plugins.lotteryNotify.lottery_database import LotteryDatabase
    print("[LotteryNotify] lottery_database.py のインポートが完了しました")
except ImportError as e:
    print(f"[LotteryNotify] lottery_database.pyが見つかりません: {e}")
    print("[LotteryNotify] まずlottery_database.pyを作成してください。")
    LotteryDatabase = None

class LotteryNotifier:
    def __init__(self, bot):
        self.bot = bot
        # ギルド設定管理用（module_name不要）
        self.db = LotteryDatabase() if LotteryDatabase else None
        self.notify_modules = {}
        self.load_notify_modules()
        # チェック中フラグ（info.pyパターン）
        self.checking = False
        self._check_task = None
        
    @property
    def enabled_guilds(self):
        """統一データベースから設定を取得"""
        if self.db is None:
            return {}
        return self.db.get_all_guild_settings()
        
    def enable_guild(self, guild_id, channel_id):
        """ギルドの通知を有効化"""
        if self.db is None:
            return False
        return self.db.set_guild_setting(guild_id, channel_id)
        
    def disable_guild(self, guild_id):
        """ギルドの通知を無効化"""
        if self.db is None:
            return False
        return self.db.remove_guild_setting(guild_id)
        
    def get_guild_channel(self, guild_id):
        """ギルドの通知チャンネルを取得"""
        if self.db is None:
            return None
        return self.db.get_guild_setting(guild_id)
        
    def load_guild_settings(self):
        """後方互換性のためのメソッド（現在は何もしない）"""
        pass
        
    def save_guild_settings(self):
        """後方互換性のためのメソッド（現在は何もしない）"""
        pass
        
    def load_notify_modules(self):
        """notifyListディレクトリから全てのPythonファイルを動的に読み込み"""
        notify_dir = os.path.join(os.path.dirname(__file__), 'lotteryNotify', 'notifyList')
        if not os.path.exists(notify_dir):
            print(f"[LotteryNotify] notifyListディレクトリが見つかりません: {notify_dir}")
            return
            
        # **/*.pyパターンでPythonファイルを検索
        py_files = glob.glob(os.path.join(notify_dir, '**', '*.py'), recursive=True)
        
        for py_file in py_files:
            if os.path.basename(py_file) == '__init__.py':
                continue
                
            try:
                # モジュール名を生成（パスからファイル名を取得）
                module_name = os.path.splitext(os.path.basename(py_file))[0]
                
                # 動的にモジュールを読み込み
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # モジュールにcheck_lottery関数があるかチェック
                    if hasattr(module, 'check_lottery'):
                        self.notify_modules[module_name] = module
                        print(f"[LotteryNotify] 読み込み完了: {module_name}")
                    else:
                        print(f"[LotteryNotify] check_lottery関数が見つかりません: {module_name}")
                        
            except Exception as e:
                print(f"[LotteryNotify] モジュール読み込みエラー {py_file}: {e}")
    
    def start_check_loop(self):
        """info.pyパターンに合わせたチェックループ開始"""
        if not self.checking:
            self.checking = True
            self._check_task = asyncio.create_task(self._check_loop())
    
    async def _check_loop(self):
        """定期チェックループ（info.pyパターン）"""
        while self.checking:
            try:
                await self.check_all_lotteries()
            except Exception as e:
                print(f"[LotteryNotify] 定期チェックエラー: {e}")
            
            await asyncio.sleep(5 * 60)
    
    async def check_all_lotteries(self):
        """全ての抽選モジュールをチェックして通知を送信"""
        enabled_guilds = self.enabled_guilds
        if not enabled_guilds:
            return
            
        notifications = []
        
        # 各モジュールの抽選をチェック
        for module_name, module in self.notify_modules.items():
            try:
                result = await module.check_lottery()
                if result:
                    notifications.extend(result if isinstance(result, list) else [result])
                    print(f"[LotteryNotify] {module_name}から{len(result if isinstance(result, list) else [result])}件の通知")
            except Exception as e:
                print(f"[LotteryNotify] {module_name}でエラー: {e}")
        
        # 通知を送信
        if notifications:
            await self.send_notifications(notifications)
            print(f"[LotteryNotify] 合計{len(notifications)}件の通知を送信")
    
    async def send_notifications(self, notifications):
        """通知メッセージを各ギルドのチャンネルに送信"""
        enabled_guilds = self.enabled_guilds
        for guild_id, channel_id in enabled_guilds.items():
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    print(f"[LotteryNotify] ギルドが見つかりません: {guild_id}")
                    continue
                    
                channel = guild.get_channel(int(channel_id))
                if not channel:
                    print(f"[LotteryNotify] チャンネルが見つかりません: {channel_id} (Guild: {guild_id})")
                    continue
                
                for notification in notifications:
                    embed = Embed(
                        title="🎰 抽選情報",
                        description=notification.get('description', '新しい抽選が見つかりました！'),
                        color=0xff6b6b,
                        timestamp=datetime.now()
                    )
                    
                    if 'title' in notification:
                        embed.add_field(name="タイトル", value=notification['title'], inline=False)
                    if 'url' in notification:
                        embed.add_field(name="URL", value=notification['url'], inline=False)
                    if 'deadline' in notification:
                        embed.add_field(name="締切", value=notification['deadline'], inline=True)
                    if 'prize' in notification:
                        embed.add_field(name="賞品", value=notification['prize'], inline=True)
                    if 'price' in notification:
                        embed.add_field(name="価格", value=notification['price'], inline=True)
                        
                    embed.set_footer(text="🎰 抽選通知システム")
                    
                    await channel.send(embed=embed)
                    print(f"[LotteryNotify] 通知送信完了: Guild {guild_id}, Channel {channel_id}")
                    
            except Exception as e:
                print(f"[LotteryNotify] 通知送信エラー (Guild: {guild_id}): {e}")

    async def send_notifications_to_guild(self, notifications, target_guild_id):
        """特定のギルドのみに通知メッセージを送信"""
        channel_id = self.get_guild_channel(target_guild_id)
        if not channel_id:
            print(f"[LotteryNotify] ギルド {target_guild_id} の通知チャンネルが設定されていません")
            return
            
        try:
            guild = self.bot.get_guild(int(target_guild_id))
            if not guild:
                print(f"[LotteryNotify] ギルドが見つかりません: {target_guild_id}")
                return
                
            channel = guild.get_channel(int(channel_id))
            if not channel:
                print(f"[LotteryNotify] チャンネルが見つかりません: {channel_id} (Guild: {target_guild_id})")
                return
            
            for notification in notifications:
                embed = Embed(
                    title="🎰 抽選情報",
                    description=notification.get('description', '新しい抽選が見つかりました！'),
                    color=0xff6b6b,
                    timestamp=datetime.now()
                )
                
                if 'title' in notification:
                    embed.add_field(name="タイトル", value=notification['title'], inline=False)
                if 'url' in notification:
                    embed.add_field(name="URL", value=notification['url'], inline=False)
                if 'deadline' in notification:
                    embed.add_field(name="締切", value=notification['deadline'], inline=True)
                if 'prize' in notification:
                    embed.add_field(name="賞品", value=notification['prize'], inline=True)
                if 'price' in notification:
                    embed.add_field(name="価格", value=notification['price'], inline=True)
                    
                embed.set_footer(text="🎰 抽選通知システム")
                
                await channel.send(embed=embed)
                print(f"[LotteryNotify] 手動チェック通知送信完了: Guild {target_guild_id}, Channel {channel_id}")
                
        except Exception as e:
            print(f"[LotteryNotify] 手動チェック通知送信エラー (Guild: {target_guild_id}): {e}")

# グローバル変数
lottery_notifier = None

def setup(bot):
    global lottery_notifier
    lottery_notifier = LotteryNotifier(bot)
    
    @commands.group()
    async def lottery(ctx):
        """
        抽選通知関連のコマンドグループ。
        """
        if ctx.invoked_subcommand is None:
            embed = Embed(
                title="🎰 抽選通知システム",
                description="利用可能なコマンド:",
                color=0x4ade80
            )
            embed.add_field(
                name="`#lottery set <channel_id>`",
                value="指定されたチャンネルで抽選通知を開始",
                inline=False
            )
            embed.add_field(
                name="`#lottery off`",
                value="現在のギルドで抽選通知を停止",
                inline=False
            )
            embed.add_field(
                name="`#lottery status`",
                value="現在の通知設定を確認",
                inline=False
            )
            embed.add_field(
                name="`#lottery check`",
                value="手動で抽選チェックを実行（デバッグ用）",
                inline=False
            )
            embed.set_footer(text="🎰 5分ごとに自動で抽選をチェックしています")
            await ctx.send(embed=embed)

    @lottery.command(name='off')
    async def lottery_off(ctx):
        """
        現在のギルドで抽選通知を無効にします。
        """
        global lottery_notifier
        if lottery_notifier is None:
            await ctx.send("抽選通知システムが初期化されていません。")
            return
            
        guild_id = str(ctx.guild.id)
        
        if lottery_notifier.get_guild_channel(guild_id):
            lottery_notifier.disable_guild(guild_id)
            
            embed = Embed(
                title="🔕 抽選通知を停止しました",
                description="このサーバーでの抽選通知が無効になりました。",
                color=0x95a5a6
            )
            await ctx.send(embed=embed)
        else:
            embed = Embed(
                title="ℹ️ 通知設定なし",
                description="このサーバーでは抽選通知が設定されていません。",
                color=0x3498db
            )
            await ctx.send(embed=embed)

    @lottery.command(name='status')
    async def lottery_status(ctx):
        """
        現在の抽選通知設定を表示します。
        """
        global lottery_notifier
        if lottery_notifier is None:
            await ctx.send("抽選通知システムが初期化されていません。")
            return
            
        guild_id = str(ctx.guild.id)
        
        embed = Embed(
            title="📊 抽選通知ステータス",
            color=0x3498db
        )
        
        # 新しいデータベースシステムを使用してチャンネル情報を取得
        channel_id = lottery_notifier.get_guild_channel(guild_id)
        if channel_id:
            channel = ctx.guild.get_channel(int(channel_id))
            channel_mention = channel.mention if channel else f"<#{channel_id}> (チャンネルが見つかりません)"
            
            embed.add_field(
                name="状態",
                value="🟢 有効",
                inline=True
            )
            embed.add_field(
                name="通知チャンネル",
                value=channel_mention,
                inline=True
            )
        else:
            embed.add_field(
                name="状態",
                value="🔴 無効",
                inline=True
            )
            
        embed.add_field(
            name="読み込み済みモジュール",
            value=f"{len(lottery_notifier.notify_modules)}個" if lottery_notifier.notify_modules else "なし",
            inline=True
        )
        
        if lottery_notifier.notify_modules:
            modules_list = ", ".join(lottery_notifier.notify_modules.keys())
            embed.add_field(
                name="モジュール一覧",
                value=modules_list,
                inline=False
            )
            
        # 全ギルドの設定数も表示
        all_guilds = lottery_notifier.enabled_guilds
        embed.add_field(
            name="システム情報",
            value=f"設定済みギルド数: {len(all_guilds)}個",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @lottery.command(name='check')
    async def lottery_check(ctx):
        """
        手動で抽選チェックを実行します（デバッグ用）。
        """
        global lottery_notifier
        if lottery_notifier is None:
            await ctx.send("抽選通知システムが初期化されていません。")
            return
        
        guild_id = str(ctx.guild.id)
        if not lottery_notifier.get_guild_channel(guild_id):
            embed = Embed(
                title="❌ 通知が無効",
                description="このサーバーでは抽選通知が設定されていません。先に `#lottery <channel_id>` で設定してください。",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)
            return
        
        # 一時的に応答
        check_message = await ctx.send("🔄 抽選チェックを開始します...")
        
        try:
            # 手動チェック実行
            notifications = []
            checked_modules = 0
            
            for module_name, module in lottery_notifier.notify_modules.items():
                try:
                    result = await module.check_lottery()
                    if result:
                        notifications.extend(result if isinstance(result, list) else [result])
                    checked_modules += 1
                except Exception as e:
                    print(f"[LotteryNotify] {module_name}でエラー: {e}")
            
            # 結果の表示
            if notifications:
                # このギルドのみに通知を送信
                await lottery_notifier.send_notifications_to_guild(notifications, guild_id)
                embed = Embed(
                    title="✅ 抽選チェック完了",
                    description=f"🎰 **{len(notifications)}件の新しい抽選** が見つかりました！\n通知を送信しました。",
                    color=0x2ecc71
                )
            else:
                embed = Embed(
                    title="ℹ️ 抽選チェック完了",
                    description="新しい抽選は見つかりませんでした。",
                    color=0x3498db
                )
            
            embed.add_field(
                name="チェック結果",
                value=f"```\n📋 チェック済みモジュール: {checked_modules}個\n🎯 検出された抽選: {len(notifications)}件\n```",
                inline=False
            )
            
            await check_message.edit(content="", embed=embed)
            
        except Exception as e:
            embed = Embed(
                title="❌ チェックエラー",
                description=f"抽選チェック中にエラーが発生しました: {str(e)}",
                color=0xe74c3c
            )
            await check_message.edit(content="", embed=embed)

    @lottery.command(name='set')
    async def set_channel(ctx, channel_id: str):
        """
        指定されたチャンネルIDで抽選通知を有効にします。
        使い方: #lottery set <channel_id>
        """
        global lottery_notifier
        if lottery_notifier is None:
            await ctx.send("抽選通知システムが初期化されていません。")
            return
            
        try:
            # チャンネルIDが数値かチェック
            int(channel_id)
            
            # チャンネルが存在するかチェック
            channel = ctx.guild.get_channel(int(channel_id))
            if not channel:
                embed = Embed(
                    title="❌ エラー",
                    description="指定されたチャンネルIDが見つかりません。",
                    color=0xe74c3c
                )
                await ctx.send(embed=embed)
                return
            
            # 設定を保存
            guild_id = str(ctx.guild.id)
            lottery_notifier.enable_guild(guild_id, channel_id)
            
            embed = Embed(
                title="✅ 抽選通知を設定しました",
                description=f"通知チャンネル: {channel.mention}",
                color=0x2ecc71
            )
            embed.add_field(
                name="読み込み済みモジュール",
                value=f"{len(lottery_notifier.notify_modules)}個",
                inline=True
            )
            
            await ctx.send(embed=embed)
            
        except ValueError:
            embed = Embed(
                title="❌ エラー",
                description="チャンネルIDは数値で指定してください。",
                color=0xe74c3c
            )
            await ctx.send(embed=embed)

    # コマンドを登録
    register_command(bot, lottery, aliases=None, admin=True)

    # info.pyのパターンに合わせて、ハンドラーがすでに存在しない場合のみ作成・開始
    if not hasattr(bot, '_lottery_notification_handler'):
        # 定期チェックタスクを管理するハンドラーを作成
        async def lottery_check_loop():
            """定期的に抽選をチェックするループ"""
            while True:
                try:
                    if lottery_notifier is not None:
                        await lottery_notifier.check_all_lotteries()
                except Exception as e:
                    print(f"[LotteryNotify] 定期チェックエラー: {e}")
                
                await asyncio.sleep(5 * 60)

        if not hasattr(bot, '_lottery_check_task'):
            bot._lottery_check_task = asyncio.create_task(lottery_check_loop())
        # ハンドラーの存在を示すフラグを設定
        bot._lottery_notification_handler = True
