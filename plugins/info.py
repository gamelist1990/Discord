import discord
from discord.ext import commands, tasks
import xml.etree.ElementTree as ET
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
import re
from plugins import register_command
from DataBase import get_guild_value, update_guild_data
from plugins.common_ui import ModalInputView


# --- デバッグ用フラグ ---
debug = True

# --- JSTタイムゾーン定義 ---
JST = timezone(timedelta(hours=9))


class VideoNotificationModal(discord.ui.Modal, title="動画通知設定"):
    def __init__(self):
        super().__init__()

    channel_url = discord.ui.TextInput(
        label="チャンネルURL",
        placeholder="YouTubeチャンネルのURLを入力してください",
        required=True,
        max_length=500,
    )

    notification_channel = discord.ui.TextInput(
        label="通知チャンネルID",
        placeholder="通知を送信するDiscordチャンネルのIDを入力",
        required=True,
        max_length=100,
    )

    check_interval = discord.ui.TextInput(
        label="チェック間隔（分）",
        placeholder="動画チェックの間隔を分単位で入力（3-60分、デフォルト: 30）",
        required=False,
        default="30",
        max_length=10,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if debug:
                print(
                    f"[DEBUG] Modal submit: guild={interaction.guild.id if interaction.guild else None}, url={self.channel_url.value}, channel={self.notification_channel.value}, interval={self.check_interval.value}"
                )

            # ギルドチェック
            if not interaction.guild:
                await interaction.response.send_message(
                    "❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True
                )
                return

            # チャンネルIDからRSSフィードURLを生成
            channel_id = await self.extract_channel_id(self.channel_url.value)
            if not channel_id:
                await interaction.response.send_message(
                    "❌ 無効なチャンネルURLです（ID取得失敗）。", ephemeral=True
                )
                return

            # チャンネル名を取得
            channel_name = await self.extract_channel_name(channel_id)
            if not channel_name:
                channel_name = channel_id  # 取得失敗時はIDを仮表示

            rss_url = (
                f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            )

            # チェック間隔のバリデーション
            interval = int(self.check_interval.value or 30)
            if interval < 1:
                await interaction.response.send_message(
                    "❌ チェック間隔は最小1分です。", ephemeral=True
                )
                return
            elif interval > 60:
                await interaction.response.send_message(
                    "❌ チェック間隔は最大60分（1時間）です。", ephemeral=True
                )
                return

            # 設定を保存
            await self.save_notification_config(
                interaction.guild.id,
                channel_id,
                channel_name,
                rss_url,
                int(self.notification_channel.value),
                interval,
            )

            if debug:
                print(
                    f"[DEBUG] 保存完了: {channel_id} {channel_name} interval={interval}"
                )

            embed = discord.Embed(
                title="✅ 動画通知設定完了",
                description=f"🎉 **{channel_name}** の動画通知が正常に設定されました！\n新着動画やライブ配信を自動でお知らせします。",
                color=0x00FF7F,  # スプリンググリーン
                timestamp=datetime.now(JST),
            )
            embed.add_field(
                name="📺 監視チャンネル", 
                value=f"```\n{channel_name}\n```", 
                inline=False
            )
            embed.add_field(
                name="🔔 通知先",
                value=f"<#{self.notification_channel.value}>",
                inline=True,
            )
            embed.add_field(
                name="⏰ チェック間隔", 
                value=f"```\n{interval}分ごと\n```", 
                inline=True
            )
            embed.add_field(
                name="🚀 ステータス", 
                value="```\n✅ 監視開始済み\n```", 
                inline=True
            )
            embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1234567890/check_green.png")
            embed.set_footer(text="📹 YouTube通知システム | 設定完了", icon_url="https://youtube.com/favicon.ico")

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            if debug:
                print(f"[DEBUG] ValueError: チャンネルIDまたはチェック間隔が無効")
            await interaction.response.send_message(
                "❌ チャンネルIDまたはチェック間隔が無効です。数値は3-60の範囲で入力してください。",
                ephemeral=True,
            )
        except Exception as e:
            if debug:
                print(f"[DEBUG] on_submit error: {e}")
            await interaction.response.send_message(
                f"❌ エラーが発生しました: {str(e)}", ephemeral=True
            )

    async def extract_channel_id(self, url):
        """YouTubeRSSAPIを使用してチャンネルIDを取得"""
        youtube_api = YouTubeRSSAPI()
        return await youtube_api.extract_channel_id(url)

    async def extract_channel_name(self, channel_id):
        """YouTubeRSSAPIを使用してチャンネル名を取得"""
        youtube_api = YouTubeRSSAPI()
        channel_info = await youtube_api.get_channel_info(channel_id)
        return channel_info["channel_name"] if channel_info else None

    async def save_notification_config(
        self, guild_id, channel_id, channel_name, rss_url, notification_channel_id, interval
    ):
        if debug:
            print(
                f"[DEBUG] save_notification_config: guild={guild_id}, channel_id={channel_id}, name={channel_name}, interval={interval}"
            )

        """通知設定をDataBase.pyに保存（チャンネル名も保存）"""
        channels = get_guild_value(guild_id, "youtube_channels", [])

        found = False
        for ch in channels:
            if ch.get("channel_id") == channel_id:
                ch.update(
                    {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "rss_url": rss_url,
                        "notification_channel": notification_channel_id,
                        "interval": interval,
                        "last_video_id": None,
                        "was_live": False,
                        "created_at": datetime.now(JST).isoformat(),
                    }
                )
                found = True
                break

        if not found:
            channels.append(
                {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "rss_url": rss_url,
                    "notification_channel": notification_channel_id,
                    "interval": interval,
                    "last_video_id": None,
                    "was_live": False,
                    "created_at": datetime.now(JST).isoformat(),
                }
            )

        update_guild_data(guild_id, "youtube_channels", channels)


class VideoNotificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        if debug:
            print("[DEBUG] VideoNotificationView initialized")

    @discord.ui.button(
        label="📹 動画通知を設定", style=discord.ButtonStyle.primary, emoji="📹"
    )
    async def setup_notification(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] setup_notification called by user={interaction.user.id}")
        modal = VideoNotificationModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="📋 設定一覧", style=discord.ButtonStyle.secondary, emoji="📋"
    )
    async def list_notifications(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] list_notifications called by user={interaction.user.id}")
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        embed = await self.create_notification_list_embed(interaction.guild.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🗑️ 設定削除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_notification(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] delete_notification called by user={interaction.user.id}")
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        # 削除用のセレクトメニューを表示
        view = DeleteNotificationView(interaction.guild.id)
        if (
            view.select.options
            and len(view.select.options) > 0
            and view.select.options[0].value != "none"
        ):
            await interaction.response.send_message(
                "削除する設定を選択してください:", view=view, ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ 削除可能な設定がありません。", ephemeral=True
            )

    @discord.ui.button(
        label="🔄 一斉更新（デバッグ）", style=discord.ButtonStyle.success, emoji="🔄"
    )
    async def force_update(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] force_update called by user={interaction.user.id}")
        """全チャンネルの即時チェック（handler不要・即時確認）"""
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        await interaction.response.send_message("⏳ 一斉更新を実行中...", ephemeral=True)
        # 全チャンネル即時チェック
        channels = get_guild_value(interaction.guild.id, "youtube_channels", [])
        handler = VideoNotificationHandler(interaction.client)
        updated = 0
        for channel_info in channels:
            await handler.check_one_channel(interaction.guild, channel_info)
            updated += 1
        await interaction.followup.send(f"✅ 一斉更新が完了しました（{updated}件チェック）", ephemeral=True)

    @discord.ui.button(
        label="💬 メッセージ設定", style=discord.ButtonStyle.secondary, emoji="💬"
    )
    async def customize_message(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] customize_message called by user={interaction.user.id}")
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        # カスタムメッセージ設定用のセレクトメニューを表示
        view = CustomMessageView(interaction.guild.id)
        if (
            view.select.options
            and len(view.select.options) > 0
            and view.select.options[0].value != "none"
        ):
            await interaction.response.send_message(
                "💬 **通知メッセージをカスタマイズ**\nメッセージをカスタマイズするチャンネルを選択してください:", 
                view=view, 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ カスタマイズ可能なチャンネルがありません。先にチャンネルを設定してください。", 
                ephemeral=True
            )

    async def create_notification_list_embed(self, guild_id):
        if debug:
            print(f"[DEBUG] create_notification_list_embed: guild_id={guild_id}")

        """設定一覧のEmbedを作成（チャンネル名・次回更新時刻を表示）"""
        embed = discord.Embed(
            title="📋 YouTube動画通知 設定一覧",
            description="🎬 **現在監視中のチャンネル一覧**\n各チャンネルの詳細情報と次回更新予定をご確認ください。",
            color=0x4169E1,  # ロイヤルブルー
            timestamp=datetime.now(),
        )

        channels = get_guild_value(guild_id, "youtube_channels", [])

        if not channels:
            embed.description = "❌ **監視中のチャンネルはありません**\n📹 「動画通知を設定」から新しいチャンネルを追加してください。"
            embed.color = 0xFF6B6B  # 薄い赤
            return embed

        for i, channel_info in enumerate(channels, 1):
            # チャンネル名優先、なければID
            channel_name = channel_info.get("channel_name") or channel_info.get("channel_id", "Unknown")
            status_emoji = "🔴" if channel_info.get("was_live", False) else "⚫"
            status_text = "ライブ中" if channel_info.get("was_live", False) else "オフライン"
            
            # カスタムメッセージ設定状況
            has_custom_video = bool(channel_info.get("custom_video_message"))
            has_custom_live = bool(channel_info.get("custom_live_message"))
            custom_status = ""
            if has_custom_video and has_custom_live:
                custom_status = "💬 動画・ライブ両方カスタム"
            elif has_custom_video:
                custom_status = "💬 動画のみカスタム"
            elif has_custom_live:
                custom_status = "💬 ライブのみカスタム"
            else:
                custom_status = "📝 デフォルトメッセージ"
            
            # 次回更新予定時刻
            last_check = channel_info.get("last_check")
            interval = channel_info.get("interval", 30)
            try:
                if last_check:
                    last_dt = datetime.fromisoformat(last_check)
                    # JSTで表示
                    next_update = last_dt + timedelta(minutes=interval)
                    next_update = next_update.astimezone(JST)
                    unix_ts = int(next_update.timestamp())
                    next_update_str = f"<t:{unix_ts}:R>"
                else:
                    next_update_str = "`未記録`"
            except Exception:
                next_update_str = "`未記録`"
                
            embed.add_field(
                name=f"📺 **{i}.** {channel_name} {status_emoji}",
                value=(
                    f"🔔 **通知先**: <#{channel_info.get('notification_channel', 'Unknown')}>\n"
                    f"⏰ **間隔**: `{interval}分`  📊 **状態**: `{status_text}`\n"
                    f"🔄 **次回更新**: {next_update_str}\n"
                    f"{custom_status}\n"
                    f"📅 **設定日**: `{channel_info.get('created_at', 'N/A')[:10]}`"
                ),
                inline=False,
            )
        
        embed.set_footer(
            text=f"📊 合計 {len(channels)} チャンネルを監視中 | YouTube通知システム", 
            icon_url="https://youtube.com/favicon.ico"
        )
        return embed


class DeleteNotificationView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        if debug:
            print(f"[DEBUG] DeleteNotificationView initialized for guild={guild_id}")
        self.guild_id = guild_id
        self.select = self.create_delete_select()
        self.add_item(self.select)

    def create_delete_select(self):
        if debug:
            print(f"[DEBUG] create_delete_select for guild={self.guild_id}")

        """削除用セレクトメニューを作成"""
        options = []

        channels = get_guild_value(self.guild_id, "youtube_channels", [])

        for channel_info in channels:
            channel_id = channel_info.get("channel_id", "Unknown")
            notification_channel = channel_info.get("notification_channel", "Unknown")
            options.append(
                discord.SelectOption(
                    label=f"チャンネルID: {channel_id}",
                    description=f"通知先: #{notification_channel}",
                    value=channel_id,
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="削除可能な設定がありません",
                    description="設定を追加してください",
                    value="none",
                )
            )

        select = discord.ui.Select(placeholder="削除する設定を選択...", options=options)

        select.callback = self.delete_callback
        return select

    async def delete_callback(self, interaction: discord.Interaction):
        if debug:
            print(f"[DEBUG] delete_callback called by user={interaction.user.id}")

        if self.select.values[0] == "none":
            await interaction.response.send_message(
                "❌ 削除可能な設定がありません。", ephemeral=True
            )
            return

        channel_id = self.select.values[0]

        # 設定を削除
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        channels = [ch for ch in channels if ch.get("channel_id") != channel_id]
        update_guild_data(self.guild_id, "youtube_channels", channels)

        embed = discord.Embed(
            title="✅ 設定削除完了",
            description=f"🗑️ **{channel_id}** の動画通知設定を削除しました。\n今後このチャンネルの通知は送信されません。",
            color=0xFF6347,  # トマト色
        )
        embed.add_field(
            name="🔧 削除されたチャンネル", 
            value=f"```\n{channel_id}\n```", 
            inline=False
        )
        embed.set_footer(text="🗑️ YouTube通知システム | 設定削除", icon_url="https://youtube.com/favicon.ico")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class VideoNotificationHandler:
    """
    YouTube動画・配信通知の状態管理・通知処理を一元化するハンドラー
    """
    def __init__(self, bot):
        self.bot = bot
        self.youtube_api = YouTubeRSSAPI()  # YouTube RSS API インスタンス
        if debug:
            print(f"[DEBUG] VideoNotificationHandler initialized for bot={bot}")

    # --- 追加: 状態管理・監視ループ・単一チャンネルチェック ---
    checking = False
    _check_task = None

    def start_check_loop(self):
        if debug:
            print("[DEBUG] start_check_loop called")
        if not self.checking:
            self.checking = True
            self._check_task = asyncio.create_task(self._check_loop())

    async def _check_loop(self):
        if debug:
            print("[DEBUG] _check_loop started")
        while self.checking:
            now = datetime.now(JST)
            for guild in self.bot.guilds:
                channels = get_guild_value(guild.id, "youtube_channels", [])
                for channel_info in channels:
                    # 各チャンネルチェック前にchannelIdで最新情報を再取得
                    channel_id = channel_info.get("channel_id")
                    if not channel_id:
                        continue
                        
                    fresh_channels = get_guild_value(guild.id, "youtube_channels", [])
                    fresh_channel_info = None
                    for ch in fresh_channels:
                        if ch.get("channel_id") == channel_id:
                            fresh_channel_info = ch
                            break
                    
                    if not fresh_channel_info:
                        continue  # チャンネルが削除された場合
                    
                    last_check = fresh_channel_info.get("last_check")
                    interval = fresh_channel_info.get("interval", 30)
                    if last_check:
                        last_dt = datetime.fromisoformat(last_check)
                        next_update = last_dt + timedelta(minutes=interval)
                        next_update = next_update.astimezone(JST)
                        if now < next_update:
                            #if debug:
                             # print(f"[DEBUG] スキップ: {channel_id} 次回更新まで {(next_update - now).total_seconds():.0f}秒")
                            continue  # まだ次回更新時刻前ならスキップ
                    await self.check_one_channel(guild, fresh_channel_info)
            await asyncio.sleep(10)  # 10秒ごとに全体ループ

    async def check_one_channel(self, guild, channel_info):
        if debug:
            print(f"[DEBUG] check_one_channel: guild={guild.id}, channel={channel_info.get('channel_id')}")
        
        channel_id = channel_info.get("channel_id")
        if not channel_id:
            if debug:
                print("[DEBUG] チャンネルIDが未設定")
            return
        
        # YouTubeRSSAPIを使用して最新動画情報を取得
        latest_video = await self.youtube_api.get_latest_video_info(channel_id)
        if not latest_video:
            if debug:
                print(f"[DEBUG] RSS取得失敗または動画なし: {channel_id}")
            return
        
        latest_video_id = latest_video["video_id"]
        
        # 初回: last_video_idがNoneなら記録のみ
        if not channel_info.get("last_video_id"):
            if debug:
                print(f"[DEBUG] 初回記録: {channel_id} → {latest_video_id}")
            self.update_channel_state(guild.id, channel_info, video_id=latest_video_id)
            return
        
        # 既に通知済みなら何もしない
        if channel_info.get("last_video_id") == latest_video_id:
            if debug:
                print(f"[DEBUG] 既に最新動画を通知済み: {latest_video_id}")
            self.update_channel_state(guild.id, channel_info)
            return
        
        # 新着動画があれば通知
        if latest_video["is_live"]:
            await self.send_live_notification(guild, channel_info, latest_video)
        else:
            await self.send_video_notification(guild, channel_info, latest_video)

        # 通知後、状態を更新
        self.update_channel_state(guild.id, channel_info, video_id=latest_video_id)
        if debug:
            print(f"[DEBUG] 新着動画通知済み: {latest_video_id}")

    async def fetch_channel_name(self, rss_url):
        """非推奨: YouTubeRSSAPIを使用してください"""
        if debug:
            print(f"[DEBUG] fetch_channel_name (deprecated): rss_url={rss_url}")
        # YouTubeRSSAPIへの移行用ラッパー
        channel_id = rss_url.split("channel_id=")[-1]
        channel_info = await self.youtube_api.get_channel_info(channel_id)
        return channel_info["channel_name"] if channel_info else None

    def get_next_update_time(self, channel_info):
        if debug:
            print(f"[DEBUG] get_next_update_time: channel_id={channel_info.get('channel_id')}")

        """次回更新予定時刻を返す"""
        last_check = channel_info.get("last_check")
        interval = channel_info.get("interval", 30)
        try:
            if last_check:
                last_dt = datetime.fromisoformat(last_check)
                return last_dt + timedelta(minutes=interval)
        except Exception:
            pass
        return None

    async def fetch_channel_data_with_retry(self, channel_id, max_retries=3):
        """非推奨: YouTubeRSSAPI.get_latest_videos()を使用してください"""
        if debug:
            print(f"[DEBUG] fetch_channel_data_with_retry (deprecated): channel_id={channel_id}")
        # YouTubeRSSAPIへの移行用ラッパー
        videos_data = await self.youtube_api.get_latest_videos(channel_id, max_retries)
        if videos_data:
            return {
                "xml_content": videos_data["xml_content"],
                "entries": [self._video_to_entry(v) for v in videos_data["videos"]],
                "channel_id": channel_id,
            }
        return None
    
    def _video_to_entry(self, video_info):
        """動画情報を旧形式のentryオブジェクト風に変換（互換性のため）"""
        # この関数は移行期間中のみ使用
        class MockElem:
            def __init__(self, text):
                self.text = text
        
        class MockEntry:
            def __init__(self, video_info):
                self.video_info = video_info
            
            def find(self, tag):
                if "videoId" in tag:
                    return MockElem(self.video_info["video_id"])
                elif "title" in tag:
                    return MockElem(self.video_info["title"])
                elif "name" in tag:
                    return MockElem(self.video_info["author"])
                elif "published" in tag:
                    return MockElem(self.video_info["published"])
                return None
        
        return MockEntry(video_info)

    async def check_if_live(self, video_id):
        """非推奨: YouTubeRSSAPI.check_if_live()を使用してください"""
        if debug:
            print(f"[DEBUG] check_if_live (deprecated): video_id={video_id}")
        return await self.youtube_api.check_if_live(video_id)

    async def send_video_notification(self, guild, channel_info, video_info):
        if debug:
            print(
                f"[DEBUG] send_video_notification: guild={guild.id}, channel={channel_info.get('channel_id')}, video={video_info.get('video_id')}"
            )

        """動画通知を送信"""
        try:
            notification_channel_id = channel_info.get("notification_channel")
            if not notification_channel_id:
                return

            channel = guild.get_channel(notification_channel_id)
            if not channel:
                return

            # カスタムメッセージがあるかチェック
            custom_message = channel_info.get("custom_video_message")
            
            if custom_message:
                # カスタムメッセージを使用（プレースホルダーを置換）
                published_dt = datetime.fromisoformat(
                    video_info["published"].replace("Z", "+00:00")
                )
                published_str = published_dt.strftime("%Y年%m月%d日 %H:%M")
                
                message = custom_message.format(
                    title=video_info["title"],
                    url=video_info["url"],
                    author=video_info["author"],
                    published=published_str
                )
                
                await channel.send(message)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] カスタム動画通知送信: {video_info['title']}"
                )
            else:
                # デフォルトのEmbed形式で送信
                published_dt = datetime.fromisoformat(
                    video_info["published"].replace("Z", "+00:00")
                )
                published_str = published_dt.strftime("%Y年%m月%d日 %H:%M")

                embed = discord.Embed(
                    title="🎬 新着動画が投稿されました！",
                    description=(
                        f"📺 **{video_info['author']}** が新しい動画を投稿しました！\n\n"
                        f"🎥 **[{video_info['title']}]({video_info['url']})**\n\n"
                        f"📅 **投稿日時**: {published_str}  |  🎯 **[今すぐ視聴する]({video_info['url']})**"
                    ),
                    color=0xFF4500,  # オレンジレッド
                    timestamp=datetime.now(JST),
                )

                # サムネイルを設定
                thumbnail_url = (
                    f"https://img.youtube.com/vi/{video_info['video_id']}/maxresdefault.jpg"
                )
                embed.set_image(url=thumbnail_url)

                embed.set_footer(
                    text=f"🎬 {video_info['author']} • YouTube新着動画通知", 
                    icon_url="https://youtube.com/favicon.ico"
                )

                await channel.send(embed=embed)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] 動画通知送信: {video_info['title']}"
                )

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 動画通知送信エラー: {e}")

    async def send_live_notification(self, guild, channel_info, video_info):
        if debug:
            print(
                f"[DEBUG] send_live_notification: guild={guild.id}, channel={channel_info.get('channel_id')}, video={video_info.get('video_id')}"
            )

        """ライブ配信通知を送信"""
        try:
            notification_channel_id = channel_info.get("notification_channel")
            if not notification_channel_id:
                return

            channel = guild.get_channel(notification_channel_id)
            if not channel:
                return

            # カスタムメッセージがあるかチェック
            custom_message = channel_info.get("custom_live_message")
            
            if custom_message:
                # カスタムメッセージを使用（プレースホルダーを置換）
                message = custom_message.format(
                    title=video_info["title"],
                    url=video_info["url"],
                    author=video_info["author"]
                )
                
                await channel.send(message)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] カスタムライブ通知送信: {video_info['title']}"
                )
            else:
                # デフォルトのEmbed形式で送信
                embed = discord.Embed(
                    title="🔴 ライブ配信が開始されました！",
                    description=f"📡 **{video_info['author']}** がライブ配信を開始しました！\n今すぐ参加して楽しみましょう 🎉",
                    color=0xFF0000,  # 鮮やかな赤
                    timestamp=datetime.now(JST),
                )

                embed.add_field(
                    name="📺 配信タイトル",
                    value=f"**[{video_info['title']}]({video_info['url']})**",
                    inline=False,
                )

                embed.add_field(
                    name="👤 チャンネル", 
                    value=f"```\n{video_info['author']}\n```", 
                    inline=True
                )

                embed.add_field(
                    name="📡 配信状態", 
                    value="```\n🟢 LIVE配信中\n```", 
                    inline=True
                )

                embed.add_field(
                    name="🎯 今すぐ視聴",
                    value=f"**[🔗 配信を見る]({video_info['url']})**",
                    inline=True,
                )

                # サムネイルを設定
                thumbnail_url = (
                    f"https://img.youtube.com/vi/{video_info['video_id']}/maxresdefault.jpg"
                )
                embed.set_image(url=thumbnail_url)

                embed.set_footer(
                    text="🔴 YouTubeライブ配信通知システム", 
                    icon_url="https://youtube.com/favicon.ico"
                )

                await channel.send(embed=embed)
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] ライブ通知送信: {video_info['title']}"
                )

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ライブ通知送信エラー: {e}")

    def update_channel_state(self, guild_id, channel_info, video_id=None):
        if debug:
            print(
                f"[DEBUG] update_channel_state: guild={guild_id}, channel={channel_info.get('channel_id')}, video_id={video_id}"
            )
        if video_id is not None:
            channel_info["last_video_id"] = video_id
        channel_info["last_check"] = datetime.now(JST).isoformat()
        channels = get_guild_value(guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == channel_info.get("channel_id"):
                channels[i] = channel_info
                break
        update_guild_data(guild_id, "youtube_channels", channels)


# --- YouTube RSS API クラス ---
class YouTubeRSSAPI:
    """
    YouTube RSS フィードを扱うためのAPI化されたクラス
    チャンネル情報の取得、動画情報の取得、ライブ判定などを統合
    """
    
    def __init__(self):
        self.session = None
        if debug:
            print("[DEBUG] YouTubeRSSAPI initialized")
    
    async def extract_channel_id(self, url):
        """YouTubeチャンネルURLからチャンネルID（UC...）を抽出"""
        if debug:
            print(f"[DEBUG] YouTubeRSSAPI.extract_channel_id: url={url}")
        
        patterns = [
            r"youtube\.com/channel/([a-zA-Z0-9_-]+)",
            r"youtube\.com/c/([a-zA-Z0-9_-]+)",
            r"youtube\.com/user/([a-zA-Z0-9_-]+)",
            r"youtube\.com/@([a-zA-Z0-9_-]+)",
        ]
        
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                val = m.group(1)
                if val.startswith("UC"):
                    return val
                # UCでなければHTMLから取得
                return await self._extract_channel_id_from_html(url)
        return None
    
    async def _extract_channel_id_from_html(self, url):
        """HTMLページからチャンネルIDを抽出"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    html = await resp.text()
                    # 1. "channelId":"UCxxxx" を探す
                    m = re.search(r'"channelId":"(UC[^"]+)"', html)
                    if m:
                        return m.group(1)
                    # 2. og:url を探す
                    m = re.search(
                        r'<meta property="og:url" content="https://www.youtube.com/channel/(UC[^"]+)">',
                        html,
                    )
                    if m:
                        return m.group(1)
        except Exception as e:
            if debug:
                print(f"[DEBUG] HTMLからのチャンネルID取得エラー: {e}")
        return None
    
    async def get_channel_info(self, channel_id):
        """チャンネル情報を取得（名前、RSS URL等）"""
        if debug:
            print(f"[DEBUG] YouTubeRSSAPI.get_channel_info: channel_id={channel_id}")
        
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        channel_name = await self._extract_channel_name_from_rss(rss_url)
        
        return {
            "channel_id": channel_id,
            "channel_name": channel_name or channel_id,
            "rss_url": rss_url
        }
    
    async def _extract_channel_name_from_rss(self, rss_url):
        """RSSフィードからチャンネル名を取得"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(rss_url) as resp:
                    if resp.status == 200:
                        xml_content = await resp.text()
                        root = ET.fromstring(xml_content)
                        title_elem = root.find(".//{http://www.w3.org/2005/Atom}title")
                        if title_elem is not None:
                            return title_elem.text
        except Exception as e:
            if debug:
                print(f"[DEBUG] RSSからのチャンネル名取得エラー: {e}")
        return None
    
    async def get_latest_videos(self, channel_id, max_retries=3):
        """チャンネルの最新動画リストを取得"""
        if debug:
            print(f"[DEBUG] YouTubeRSSAPI.get_latest_videos: channel_id={channel_id}")
        
        for attempt in range(max_retries):
            try:
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(rss_url) as response:
                        if response.status == 200:
                            xml_content = await response.text()
                            return self._parse_rss_videos(xml_content, channel_id)
                        elif response.status == 429:  # Rate limit
                            wait_time = 60 * (attempt + 1)
                            if debug:
                                print(f"[DEBUG] レート制限: {wait_time}秒待機")
                            await asyncio.sleep(wait_time)
                        else:
                            if debug:
                                print(f"[DEBUG] HTTP {response.status}: {channel_id}")
                            return None
            except Exception as e:
                if debug:
                    print(f"[DEBUG] RSS取得エラー (試行 {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5 * (attempt + 1))
        return None
    
    def _parse_rss_videos(self, xml_content, channel_id):
        """RSS XMLから動画情報をパース"""
        try:
            root = ET.fromstring(xml_content)
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            
            videos = []
            for entry in entries:
                video_info = self._parse_video_entry(entry)
                if video_info:
                    videos.append(video_info)
            
            return {
                "channel_id": channel_id,
                "videos": videos,
                "xml_content": xml_content
            }
        except Exception as e:
            if debug:
                print(f"[DEBUG] RSS解析エラー: {e}")
            return None
    
    def _parse_video_entry(self, entry):
        """個別の動画エントリーをパース"""
        try:
            video_id_elem = entry.find("{http://www.youtube.com/xml/schemas/2015}videoId")
            title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
            author_elem = entry.find("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
            published_elem = entry.find("{http://www.w3.org/2005/Atom}published")
            
            if video_id_elem is None:
                return None
            
            video_id = video_id_elem.text
            return {
                "video_id": video_id,
                "title": title_elem.text if title_elem is not None else "No Title",
                "author": author_elem.text if author_elem is not None else "Unknown",
                "published": published_elem.text if published_elem is not None else datetime.now(JST).isoformat(),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        except Exception as e:
            if debug:
                print(f"[DEBUG] 動画エントリー解析エラー: {e}")
            return None
    
    async def check_if_live(self, video_id):
        """動画がライブ配信かどうかをチェック"""
        if debug:
            print(f"[DEBUG] YouTubeRSSAPI.check_if_live: video_id={video_id}")
        
        try:
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url, timeout=timeout) as response:
                    if response.status != 200:
                        return False
                    content = await response.text()
                    is_live = (
                        '"isLive":true' in content
                        or '"isLiveContent":true' in content
                        or "hlsManifestUrl" in content
                    )
                    await asyncio.sleep(1)  # Rate limiting
                    return is_live
        except asyncio.TimeoutError:
            if debug:
                print(f"[DEBUG] ライブ判定タイムアウト: {video_id}")
            return False
        except Exception as e:
            if debug:
                print(f"[DEBUG] ライブ判定エラー: {e}")
            return False
    
    async def get_latest_video_info(self, channel_id):
        """チャンネルの最新動画情報を取得（通知チェック用）"""
        videos_data = await self.get_latest_videos(channel_id)
        if not videos_data or not videos_data["videos"]:
            return None
        
        latest_video = videos_data["videos"][0]
        is_live = await self.check_if_live(latest_video["video_id"])
        latest_video["is_live"] = is_live
        
        return latest_video


# --- infoコマンド本体（Cog不要、help.py方式） ---
@commands.command()
async def info(ctx):
    """
    動画通知機能の設定画面を表示します。
    YouTubeチャンネルの新着動画とライブ配信を設定されたチェック間隔でリアルタイム監視し、
    チェック間隔内に投稿された動画・開始された配信を通知します。
    """
    embed = discord.Embed(
        title="📹 YouTube動画・配信通知システム",
        description="🎬 **YouTubeチャンネルの新着動画とライブ配信を自動で通知**\n"
        "XMLフィード（RSS）を使用してAPIを使わずにリアルタイム監視します！\n"
        "⚡ **設定されたチェック間隔で自動監視** — 投稿・配信開始を即座に検知",
        color=0xFF6B35,  
    )

    embed.add_field(
        name="## 主要機能",
        value="```diff\n"
        "+ YouTubeチャンネルの新着動画通知\n"
        "+ 🔴 ライブ配信開始通知（ベータ版）\n"
        "+ リアルタイム監視システム\n"
        "+ 複数チャンネル同時監視\n"
        "+ XMLフィード活用（API不要）\n"
        "+ 高度な状態管理\n"
        "+ 💬 カスタム通知メッセージ\n"
        "```",
        inline=False,
    )

    embed.add_field(
        name="🔗 対応URL形式",
        value="```\n"
        "✅ youtube.com/channel/UC...\n"
        "✅ youtube.com/c/チャンネル名\n"
        "✅ youtube.com/user/ユーザー名\n"
        "✅ youtube.com/@ハンドル名\n"
        "```",
        inline=True,
    )

    embed.add_field(
        name="⚙️ 監視システム",
        value="```\n"
        "⏰ 設定間隔でチェック実行\n"
        "🎬 通常動画：専用Embed\n"
        "🔴 ライブ配信：専用Embed\n"
        "🛡️ レート制限対策完備\n"
        "```",
        inline=True,
    )

    embed.add_field(
        name="💬 カスタマイズ機能",
        value="```\n"
        "� 動画・ライブ通知メッセージ\n"
        "� プレースホルダー対応\n"
        "🎨 チャンネル別個別設定\n"
        "🔄 デフォルトに戻す機能\n"
        "```",
        inline=True,
    )

    embed.set_footer(
        text="🚀 下のボタンから設定を開始 | ベータ版機能を含みます",
        icon_url="https://youtube.com/favicon.ico"
    )
    
    embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1234567890/youtube_logo.png")

    view = VideoNotificationView()
    await ctx.send(embed=embed, view=view)


class CustomMessageView(discord.ui.View):
    """カスタムメッセージ設定用のセレクトメニュー"""
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        if debug:
            print(f"[DEBUG] CustomMessageView initialized for guild={guild_id}")
        self.guild_id = guild_id
        self.select = self.create_message_select()
        self.add_item(self.select)

    def create_message_select(self):
        if debug:
            print(f"[DEBUG] create_message_select for guild={self.guild_id}")

        """カスタムメッセージ設定用セレクトメニューを作成"""
        options = []

        channels = get_guild_value(self.guild_id, "youtube_channels", [])

        for channel_info in channels:
            channel_id = channel_info.get("channel_id", "Unknown")
            channel_name = channel_info.get("channel_name") or channel_id
            notification_channel = channel_info.get("notification_channel", "Unknown")
            
            # カスタムメッセージの設定状況を表示
            has_custom = bool(channel_info.get("custom_video_message") or channel_info.get("custom_live_message"))
            status_text = "✅ カスタム設定済み" if has_custom else "📝 デフォルト"
            
            options.append(
                discord.SelectOption(
                    label=f"{channel_name}",
                    description=f"通知先: #{notification_channel} | {status_text}",
                    value=channel_id,
                    emoji="💬"
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="カスタマイズ可能なチャンネルがありません",
                    description="先にチャンネルを設定してください",
                    value="none",
                )
            )

        select = discord.ui.Select(placeholder="メッセージをカスタマイズするチャンネルを選択...", options=options)
        select.callback = self.message_callback
        return select

    async def message_callback(self, interaction: discord.Interaction):
        if debug:
            print(f"[DEBUG] message_callback called by user={interaction.user.id}")

        if self.select.values[0] == "none":
            await interaction.response.send_message(
                "❌ カスタマイズ可能なチャンネルがありません。", ephemeral=True
            )
            return

        channel_id = self.select.values[0]
        
        # 現在のチャンネル情報を取得
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        channel_info = None
        for ch in channels:
            if ch.get("channel_id") == channel_id:
                channel_info = ch
                break
        
        if not channel_info:
            await interaction.response.send_message(
                "❌ チャンネル情報が見つかりません。", ephemeral=True
            )
            return

        # カスタムメッセージ設定画面を表示
        view = CustomMessageTypeView(self.guild_id, channel_id, channel_info)
        
        channel_name = channel_info.get("channel_name") or channel_id
        embed = discord.Embed(
            title="💬 通知メッセージのカスタマイズ",
            description=f"📺 **{channel_name}** の通知メッセージを設定できます。\n\n設定したいメッセージの種類を選択してください：",
            color=0x9932CC,  # ダークバイオレット
        )
        
        # 現在の設定状況を表示
        current_video = channel_info.get("custom_video_message", "デフォルト")
        current_live = channel_info.get("custom_live_message", "デフォルト")
        
        embed.add_field(
            name="🎬 動画通知メッセージ",
            value=f"```\n{current_video[:100]}{'...' if len(current_video) > 100 else ''}\n```" if current_video != "デフォルト" else "`デフォルトメッセージを使用`",
            inline=False
        )
        
        embed.add_field(
            name="🔴 ライブ通知メッセージ",
            value=f"```\n{current_live[:100]}{'...' if len(current_live) > 100 else ''}\n```" if current_live != "デフォルト" else "`デフォルトメッセージを使用`",
            inline=False
        )
        
        embed.add_field(
            name="📝 使用可能なプレースホルダー",
            value=(
                "`{title}` - 動画/配信タイトル\n"
                "`{url}` - 動画/配信URL\n"
                "`{author}` - チャンネル名\n"
                "`{published}` - 公開日時（動画のみ）"
            ),
            inline=False
        )
        
        embed.set_footer(text="💬 YouTube通知メッセージカスタマイズ", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class CustomMessageTypeView(discord.ui.View):
    """動画/ライブメッセージの選択画面"""
    def __init__(self, guild_id, channel_id, channel_info):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.channel_info = channel_info
        if debug:
            print(f"[DEBUG] CustomMessageTypeView initialized: guild={guild_id}, channel={channel_id}")

    @discord.ui.button(label="🎬 動画通知メッセージ", style=discord.ButtonStyle.primary, emoji="🎬")
    async def video_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if debug:
            print(f"[DEBUG] video_message button clicked by user={interaction.user.id}")
        
        current_message = self.channel_info.get("custom_video_message", "")
        
        view = ModalInputView(
            label="💬 動画通知メッセージを設定",
            modal_title="🎬 動画通知メッセージのカスタマイズ",
            text_label="動画通知メッセージ",
            placeholder="カスタムメッセージを入力 | {title} {url} {author} {published} が使用可能",
            input_style="paragraph",
            min_length=1,
            max_length=2000,
            on_submit=self.save_video_message,
            ephemeral=True
        )
        
        # 現在のメッセージがある場合は初期値として設定
        if current_message:
            # ModalInputViewに初期値を設定する方法を追加する必要がある場合
            pass
            
        await interaction.response.send_message(
            f"🎬 **動画通知メッセージの設定**\n\n現在の設定: `{current_message or 'デフォルト'}`\n\n"
            f"📝 **使用可能なプレースホルダー:**\n"
            f"`{{title}}` - 動画タイトル\n"
            f"`{{url}}` - 動画URL\n"
            f"`{{author}}` - チャンネル名\n"
            f"`{{published}}` - 公開日時\n\n"
            f"下のボタンを押してメッセージを編集してください:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="🔴 ライブ通知メッセージ", style=discord.ButtonStyle.danger, emoji="🔴")
    async def live_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if debug:
            print(f"[DEBUG] live_message button clicked by user={interaction.user.id}")
        
        current_message = self.channel_info.get("custom_live_message", "")
        
        view = ModalInputView(
            label="💬 ライブ通知メッセージを設定",
            modal_title="🔴 ライブ通知メッセージのカスタマイズ",
            text_label="ライブ通知メッセージ",
            placeholder="ライブ通知メッセージを入力 | {title} {url} {author} が使用可能",
            input_style="paragraph",
            min_length=1,
            max_length=2000,
            on_submit=self.save_live_message,
            ephemeral=True
        )
        
        await interaction.response.send_message(
            f"🔴 **ライブ通知メッセージの設定**\n\n現在の設定: `{current_message or 'デフォルト'}`\n\n"
            f"📝 **使用可能なプレースホルダー:**\n"
            f"`{{title}}` - 配信タイトル\n"
            f"`{{url}}` - 配信URL\n"
            f"`{{author}}` - チャンネル名\n\n"
            f"下のボタンを押してメッセージを編集してください:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="🔄 デフォルトに戻す", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def reset_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        if debug:
            print(f"[DEBUG] reset_messages button clicked by user={interaction.user.id}")
        
        # カスタムメッセージを削除してデフォルトに戻す
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == self.channel_id:
                if "custom_video_message" in ch:
                    del ch["custom_video_message"]
                if "custom_live_message" in ch:
                    del ch["custom_live_message"]
                channels[i] = ch
                break
        
        update_guild_data(self.guild_id, "youtube_channels", channels)
        
        embed = discord.Embed(
            title="✅ デフォルトメッセージに戻しました",
            description=f"📺 **{self.channel_info.get('channel_name', self.channel_id)}** の通知メッセージをデフォルトに戻しました。",
            color=0x32CD32  # ライムグリーン
        )
        embed.set_footer(text="🔄 メッセージリセット完了", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def save_video_message(self, interaction, value, recipient, view):
        """動画通知メッセージを保存"""
        if debug:
            print(f"[DEBUG] save_video_message: guild={self.guild_id}, channel={self.channel_id}, message_length={len(value)}")
        
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == self.channel_id:
                ch["custom_video_message"] = value
                channels[i] = ch
                break
        
        update_guild_data(self.guild_id, "youtube_channels", channels)
        
        embed = discord.Embed(
            title="✅ 動画通知メッセージを保存しました",
            description=f"🎬 **{self.channel_info.get('channel_name', self.channel_id)}** の動画通知メッセージを更新しました。",
            color=0x32CD32
        )
        embed.add_field(
            name="💬 新しいメッセージ",
            value=f"```\n{value[:500]}{'...' if len(value) > 500 else ''}\n```",
            inline=False
        )
        embed.set_footer(text="🎬 動画メッセージ設定完了", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def save_live_message(self, interaction, value, recipient, view):
        """ライブ通知メッセージを保存"""
        if debug:
            print(f"[DEBUG] save_live_message: guild={self.guild_id}, channel={self.channel_id}, message_length={len(value)}")
        
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == self.channel_id:
                ch["custom_live_message"] = value
                channels[i] = ch
                break
        
        update_guild_data(self.guild_id, "youtube_channels", channels)
        
        embed = discord.Embed(
            title="✅ ライブ通知メッセージを保存しました",
            description=f"🔴 **{self.channel_info.get('channel_name', self.channel_id)}** のライブ通知メッセージを更新しました。",
            color=0x32CD32
        )
        embed.add_field(
            name="💬 新しいメッセージ",
            value=f"```\n{value[:500]}{'...' if len(value) > 500 else ''}\n```",
            inline=False
        )
        embed.set_footer(text="🔴 ライブメッセージ設定完了", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


def setup(bot):
    register_command(
        bot,
        info,
        aliases=None,
        admin=False
    )
    if not hasattr(bot, '_video_notification_handler'):
        handler = VideoNotificationHandler(bot)
        handler.start_check_loop()
        bot._video_notification_handler = handler
