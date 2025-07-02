import discord
import asyncio
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
import re
from plugins import register_command
from DataBase import get_guild_value, update_guild_data
from plugins.common_ui import ModalInputView
from lib.youtubeRSS import YoutubeRssApi, YoutubeLiveStatus, YoutubeVideoType


# --- デバッグ用フラグ ---
debug = True  # 問題解決のためデバッグを有効化

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
        youtube_api = YoutubeRssApi(debug_mode=debug)
        return youtube_api.extract_channel_id(url)

    async def extract_channel_name(self, channel_id):
        """YouTubeRSSAPIを使用してチャンネル名を取得"""
        youtube_api = YoutubeRssApi(debug_mode=debug)
        return youtube_api.get_channel_name(channel_id)

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
                # 既存の状態を保持して更新
                existing_last_video_id = ch.get("last_video_id")
                existing_last_live_video_id = ch.get("last_live_video_id")
                existing_last_live_status = ch.get("last_live_status", "none")
                existing_was_live = ch.get("was_live", False)
                existing_last_check = ch.get("last_check")
                
                ch.update(
                    {
                        "channel_id": channel_id,
                        "channel_name": channel_name,
                        "rss_url": rss_url,
                        "notification_channel": notification_channel_id,
                        "interval": interval,
                        "last_video_id": existing_last_video_id,
                        "last_live_video_id": existing_last_live_video_id,
                        "last_live_status": existing_last_live_status,
                        "was_live": existing_was_live,
                        "last_check": existing_last_check,
                        "notification_mode": ch.get("notification_mode", "embed"),  # 通知モード保持
                        "role_mention": ch.get("role_mention", ""),  # ロールメンション保持
                        "created_at": ch.get("created_at", datetime.now(JST).isoformat()),
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
                    "last_live_video_id": None,  # ライブ配信専用の動画ID管理
                    "last_live_status": "none",  # ライブ配信の状態管理
                    "was_live": False,
                    "notification_mode": "embed",  # 新規チャンネルはEmbedモード
                    "role_mention": "",  # 新規チャンネルはロールメンションなし
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
        label="動画通知を設定", style=discord.ButtonStyle.primary, emoji="📹"
    )
    async def setup_notification(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] setup_notification called by user={interaction.user.id}")
        modal = VideoNotificationModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="設定一覧", style=discord.ButtonStyle.secondary, emoji="📋"
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

    @discord.ui.button(label="設定削除", style=discord.ButtonStyle.danger, emoji="🗑️")
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
        label="一斉更新（デバッグ）", style=discord.ButtonStyle.success, emoji="🔄"
    )
    async def force_update(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] force_update called by user={interaction.user.id}")
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)  # ここで応答を保留
        channels = get_youtube_channels_with_migration(interaction.guild.id)
        handler = VideoNotificationHandler(interaction.client)
        updated = 0
        for channel_info in channels:
            await handler.check_one_channel(interaction.guild, channel_info)
            updated += 1
        await interaction.followup.send(f"✅ 一斉更新が完了しました（{updated}件チェック）", ephemeral=True)

    @discord.ui.button(
        label="通知モード設定", style=discord.ButtonStyle.secondary, emoji="⚙️"
    )
    async def notification_mode(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if debug:
            print(f"[DEBUG] notification_mode called by user={interaction.user.id}")
        if not interaction.guild:
            await interaction.response.send_message(
                "❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True
            )
            return
        # 通知モード設定用のセレクトメニューを表示
        view = NotificationModeView(interaction.guild.id)
        if (
            view.select.options
            and len(view.select.options) > 0
            and view.select.options[0].value != "none"
        ):
            await interaction.response.send_message(
                "⚙️ **通知モードを設定**\n通知モードを変更するチャンネルを選択してください:\n\n"
                "📝 **Embedモード**: リッチな埋め込み形式で詳細情報を表示\n"
                "🔗 **URLモード**: 動画URLのみを送信（軽量・シンプル）", 
                view=view, 
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ 設定可能なチャンネルがありません。先にチャンネルを設定してください。", 
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

        channels = get_youtube_channels_with_migration(guild_id)

        if not channels:
            embed.description = "❌ **監視中のチャンネルはありません**\n📹 「動画通知を設定」から新しいチャンネルを追加してください。"
            embed.color = 0xFF6B6B  # 薄い赤
            return embed

        for i, channel_info in enumerate(channels, 1):
            # チャンネル名優先、なければID
            channel_name = channel_info.get("channel_name") or channel_info.get("channel_id", "Unknown")
            
            # 新しいライブ状態管理を使用（was_liveとlast_live_statusの組み合わせ）
            last_live_status = channel_info.get("last_live_status", "none")
            was_live = channel_info.get("was_live", False)
            last_video_id = channel_info.get("last_video_id")
            last_live_video_id = channel_info.get("last_live_video_id")
            
            # より詳細なライブ状態表示
            if last_live_status == "live" and was_live:
                status_emoji = "🔴"
                status_text = "ライブ配信中"
            else:
                status_emoji = "⚫"
                status_text = "オフライン"
            
            # 最新動画・配信情報の表示（ID短縮）
            video_info = ""
            if last_live_video_id:
                video_info += f"🔴 **最新ライブ**: `{last_live_video_id[:11]}...` ({last_live_status})\n"
            if last_video_id:
                video_info += f"🎬 **最新動画**: `{last_video_id[:11]}...`\n"
            
            # 通知モード設定状況
            notification_mode = channel_info.get("notification_mode", "embed")
            if notification_mode == "url":
                mode_text = "🔗 URLモード（軽量）"
                mode_emoji = "🔗"
            else:
                mode_text = "� Embedモード（詳細）"
                mode_emoji = "📝"
            
            # ロールメンション設定状況
            role_mention = channel_info.get("role_mention", "")
            if role_mention:
                role_text = f"� ロールメンション: <@&{role_mention}>"
            else:
                role_text = "� ロールメンション: なし"
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
                    f"{video_info}"
                    f"🔄 **次回更新**: {next_update_str}\n"
                    f"{mode_emoji} **通知形式**: {mode_text}\n"
                    f"{role_text}\n"
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

        channels = get_youtube_channels_with_migration(self.guild_id)

        for channel_info in channels:
            channel_id = channel_info.get("channel_id", "Unknown")
            channel_name = channel_info.get("channel_name") or channel_id
            notification_channel = channel_info.get("notification_channel", "Unknown")
            options.append(
                discord.SelectOption(
                    label=f"チャンネル名: {channel_name}",
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
        # チャンネル名取得
        channel_name = None
        for ch in channels:
            if ch.get("channel_id") == channel_id:
                channel_name = ch.get("channel_name") or channel_id
                break
        channels = [ch for ch in channels if ch.get("channel_id") != channel_id]
        update_guild_data(self.guild_id, "youtube_channels", channels)

        embed = discord.Embed(
            title="✅ 設定削除完了",
            description=f"🗑️ **{channel_name or channel_id}** の動画通知設定を削除しました。\n今後このチャンネルの通知は送信されません。",
            color=0xFF6347,  # トマト色
        )
        embed.add_field(
            name="🔧 削除されたチャンネル", 
            value=f"```\n{channel_name or channel_id}\n```", 
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
        self.youtube_api = YoutubeRssApi(debug_mode=True)  # YouTube RSS API インスタンス
        if debug:
            print(f"[DEBUG] VideoNotificationHandler initialized for bot={bot}")
    
    # --- 状態管理・監視ループ・単一チャンネルチェック ---
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
                channels = get_youtube_channels_with_migration(guild.id)
                for channel_info in channels:
                    # 各チャンネルチェック前にchannelIdで最新情報を再取得
                    channel_id = channel_info.get("channel_id")
                    if not channel_id:
                        continue
                        
                    fresh_channels = get_youtube_channels_with_migration(guild.id)
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
        
        # 最新動画情報をAPIで一括取得
        latest_video = self.youtube_api.get_latest_video_info(channel_id)
        if not latest_video:
            if debug:
                print(f"[DEBUG] 最新動画情報の取得失敗: {channel_id}")
            return
        
        latest_video_id = latest_video.video_id
        latest_live_status = latest_video.live_status
        is_live_content = latest_live_status in [YoutubeLiveStatus.LIVE, YoutubeLiveStatus.UPCOMING, YoutubeLiveStatus.ENDED]
        
        # 前回の状態を取得
        last_live_status = channel_info.get("last_live_status", YoutubeLiveStatus.NONE)
        last_live_video_id = channel_info.get("last_live_video_id")
        last_video_id = channel_info.get("last_video_id")
        was_live = channel_info.get("was_live", False)
        
        if debug:
            print(f"[DEBUG] 状態比較 - 動画ID: {latest_video_id}, ライブ状態: {latest_live_status}, 前回ライブ状態: {last_live_status}")
            print(f"[DEBUG] 前回動画ID: {last_video_id}, 前回ライブ動画ID: {last_live_video_id}, was_live: {was_live}")
        
        # 初回記録
        if not last_video_id and not last_live_video_id:
            if is_live_content:
                self.update_channel_state(guild.id, channel_info, live_video_id=latest_video_id, live_status=latest_live_status)
            else:
                self.update_channel_state(guild.id, channel_info, video_id=latest_video_id, live_status=YoutubeLiveStatus.NONE)
            return
        
        # === 配信コンテンツの処理 ===
        if is_live_content:
            # 配信コンテンツとして処理
            should_notify_live = last_live_video_id != latest_video_id
            self.update_channel_state(guild.id, channel_info, live_video_id=latest_video_id, live_status=latest_live_status)
            if should_notify_live:
                await self.send_live_notification(guild, channel_info, latest_video)
                if debug:
                    print(f"[DEBUG] 配信通知送信: {latest_video_id}")

            # 配信コンテンツの場合は動画通知を絶対に送信しない
            if debug:
                print(f"[DEBUG] 配信コンテンツのため動画通知をスキップ: {latest_video_id}")
            return

        # 通常動画の処理
        else:
            # 通常動画として処理
            should_notify_video = last_video_id != latest_video_id and last_live_video_id != latest_video_id
            self.update_channel_state(guild.id, channel_info, video_id=latest_video_id, live_status=YoutubeLiveStatus.NONE)
            if should_notify_video:
                await self.send_video_notification(guild, channel_info, latest_video)
                if debug:
                    print(f"[DEBUG] 動画通知送信: {latest_video_id}")
        
        if debug:
            print(f"[DEBUG] チェック完了: {latest_video_id}, live={latest_live_status}, is_live_content={is_live_content}")

    def update_channel_state(self, guild_id, channel_info, video_id=None, live_video_id=None, live_status=None):
        if debug:
            print(
                f"[DEBUG] update_channel_state: guild={guild_id}, channel={channel_info.get('channel_id')}, video_id={video_id}, live_video_id={live_video_id}, live_status={live_status}"
            )
        
        # 通常動画IDの更新
        if video_id is not None:
            channel_info["last_video_id"] = video_id
        
        # ライブ配信関連の更新
        if live_video_id is not None:
            channel_info["last_live_video_id"] = live_video_id
        
        if live_status is not None:
            channel_info["last_live_status"] = live_status
            # was_liveをライブ状態に基づいて更新
            channel_info["was_live"] = (live_status in ["live", "upcoming", "ended"])
        
        # live_video_idがNoneに設定された場合（配信終了時）
        if live_video_id is None and "last_live_video_id" in channel_info:
            channel_info["last_live_video_id"] = None
            channel_info["last_live_status"] = "none"
            channel_info["was_live"] = False
            if debug:
                print(f"[DEBUG] 配信状態をリセット: {channel_info.get('channel_id')}")
        
        # 最終チェック時刻を更新
        channel_info["last_check"] = datetime.now(JST).isoformat()
        
        # データベースに保存
        channels = get_guild_value(guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == channel_info.get("channel_id"):
                channels[i] = channel_info
                break
        update_guild_data(guild_id, "youtube_channels", channels)
        
        if debug:
            print(f"[DEBUG] 状態更新完了: video_id={channel_info.get('last_video_id')}, live_video_id={channel_info.get('last_live_video_id')}, live_status={channel_info.get('last_live_status')}, was_live={channel_info.get('was_live')}")

    # 通知送信メソッドを追加
    async def send_video_notification(self, guild, channel_info, video_info):
        """通常動画通知を送信"""
        try:
            notification_channel_id = channel_info.get("notification_channel")
            if not notification_channel_id:
                return

            channel = guild.get_channel(notification_channel_id)
            if not channel:
                return

            # ライブ配信コンテンツでないことを再確認
            live_status = video_info.live_status
            if live_status in [YoutubeLiveStatus.LIVE, YoutubeLiveStatus.UPCOMING, YoutubeLiveStatus.ENDED]:
                if debug:
                    print(f"[DEBUG] 配信コンテンツのため動画通知をスキップ: {video_info.video_id}")
                return

            # 通知モードを確認
            notification_mode = channel_info.get("notification_mode", "embed")
            role_mention = channel_info.get("role_mention", "")
            
            if notification_mode == "url":
                # URLモード: 動画URLのみ送信
                message = video_info.url
                if role_mention:
                    message = f"<@&{role_mention}> {message}"
                
                await channel.send(message)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] URL動画通知送信: {video_info.title}")
            else:
                # Embedモード: リッチな埋め込み形式で送信
                published_dt = datetime.fromisoformat(
                    video_info.published.replace("Z", "+00:00")
                )
                published_str = published_dt.strftime("%Y年%m月%d日 %H:%M")

                embed = discord.Embed(
                    title="🎬 新着動画が投稿されました！",
                    description=(
                        f"📺 **{video_info.author}** が新しい動画を投稿しました！\n\n"
                        f"🎥 **[{video_info.title}]({video_info.url})**\n\n"
                        f"📅 **投稿日時**: {published_str}  |  🎯 **[今すぐ視聴する]({video_info.url})**"
                    ),
                    color=0xFF4500,  # オレンジレッド
                    timestamp=datetime.now(JST),
                )

                # サムネイルを設定
                thumbnail_url = f"https://img.youtube.com/vi/{video_info.video_id}/maxresdefault.jpg"
                embed.set_image(url=thumbnail_url)

                embed.set_footer(
                    text=f"🎬 {video_info.author} • YouTube新着動画通知", 
                    icon_url="https://youtube.com/favicon.ico"
                )

                content = f"<@&{role_mention}>" if role_mention else None
                await channel.send(content=content, embed=embed)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Embed動画通知送信: {video_info.title}")

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 動画通知送信エラー: {e}")

    async def send_live_notification(self, guild, channel_info, video_info):
        """ライブ配信通知を送信"""
        try:
            notification_channel_id = channel_info.get("notification_channel")
            if not notification_channel_id:
                return

            channel = guild.get_channel(notification_channel_id)
            if not channel:
                return

            live_status = video_info.live_status
            
            # 通知モードを確認
            notification_mode = channel_info.get("notification_mode", "embed")
            role_mention = channel_info.get("role_mention", "")
            
            if notification_mode == "url":
                # URLモード: 配信URLのみ送信
                message = video_info.url
                if role_mention:
                    message = f"<@&{role_mention}> {message}"
                
                await channel.send(message)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] URL配信通知送信: {video_info.title} (status: {live_status})")
            else:
                # Embedモード: リッチな埋め込み形式で送信
                if live_status == YoutubeLiveStatus.LIVE:
                    title = "🔴 ライブ配信が開始されました！"
                    description = f"📺 **{video_info.author}** がライブ配信を開始しました！\n今すぐ視聴してライブ配信をお楽しみください。"
                    color = 0xFF0000  # 赤色
                    status_text = "配信中"
                else:
                    title = "🎬 新しい配信が開始されました！"
                    description = f"📺 **{video_info.author}** が新しい配信を開始しました！"
                    color = 0xFF4500  # オレンジレッド
                    status_text = "配信中"

                embed = discord.Embed(
                    title=title,
                    description=description,
                    color=color,
                    timestamp=datetime.now(JST),
                )

                embed.add_field(
                    name="📺 配信タイトル",
                    value=f"**[{video_info.title}]({video_info.url})**",
                    inline=False,
                )

                embed.add_field(
                    name="👤 チャンネル", 
                    value=f"```\n{video_info.author}\n```", 
                    inline=True
                )

                embed.add_field(
                    name="📡 配信状態", 
                    value=f"```\n{status_text}\n```", 
                    inline=True
                )

                embed.add_field(
                    name="🎯 今すぐ視聴",
                    value=f"**[🔗 配信を見る]({video_info.url})**",
                    inline=True,
                )

                # サムネイルを設定
                thumbnail_url = f"https://img.youtube.com/vi/{video_info.video_id}/maxresdefault.jpg"
                embed.set_image(url=thumbnail_url)

                embed.set_footer(
                    text="🔴 YouTubeライブ配信通知システム", 
                    icon_url="https://youtube.com/favicon.ico"
                )

                content = f"<@&{role_mention}>" if role_mention else None
                await channel.send(content=content, embed=embed)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Embed配信通知送信: {video_info.title}")

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 配信通知送信エラー: {e}")

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
        "+ ⚙️ Embed/URLモード選択\n"
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
        name="⚙️ 通知モード",
        value="```\n"
        "📝 Embedモード：詳細表示\n"
        "🔗 URLモード：軽量・シンプル\n"
        "� ロールメンション対応\n"
        "🛡️ レート制限対策完備\n"
        "```",
        inline=True,
    )

    embed.add_field(
        name="🎯 軽量化設計",
        value="```\n"
        "⚡ コード大幅削減\n"
        "🔗 URLモード：最小負荷\n"
        "📝 Embedモード：リッチ表示\n"
        "� 高速処理・安定動作\n"
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


class NotificationModeView(discord.ui.View):
    """通知モード設定用のセレクトメニュー"""
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        if debug:
            print(f"[DEBUG] NotificationModeView initialized for guild={guild_id}")
        self.guild_id = guild_id
        self.select = self.create_mode_select()
        self.add_item(self.select)

    def create_mode_select(self):
        if debug:
            print(f"[DEBUG] create_mode_select for guild={self.guild_id}")

        """通知モード設定用セレクトメニューを作成"""
        options = []

        channels = get_guild_value(self.guild_id, "youtube_channels", [])

        for channel_info in channels:
            channel_id = channel_info.get("channel_id", "Unknown")
            channel_name = channel_info.get("channel_name") or channel_id
            notification_channel = channel_info.get("notification_channel", "Unknown")
            
            # 現在の通知モード
            current_mode = channel_info.get("notification_mode", "embed")
            mode_text = "Embed" if current_mode == "embed" else "URL"
            
            options.append(
                discord.SelectOption(
                    label=f"{channel_name[:45]}{'...' if len(channel_name) > 45 else ''}",
                    description=f"現在: {mode_text}モード | 通知先: #{notification_channel}",
                    value=channel_id,
                    emoji="�"
                )
            )

        if not options:
            options.append(
                discord.SelectOption(
                    label="設定可能なチャンネルなし",
                    description="先にYouTubeチャンネルを設定してください",
                    value="none",
                    emoji="❌"
                )
            )

        select = discord.ui.Select(
            placeholder="通知モードを変更するチャンネルを選択...",
            options=options[:25]  # Discord制限
        )
        select.callback = self.select_callback
        return select

    async def select_callback(self, interaction: discord.Interaction):
        if debug:
            print(f"[DEBUG] NotificationModeView select_callback: user={interaction.user.id}, value={self.select.values[0]}")
        
        if self.select.values[0] == "none":
            await interaction.response.send_message(
                "❌ 設定可能なチャンネルがありません。", 
                ephemeral=True
            )
            return

        channel_id = self.select.values[0]
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        
        channel_info = None
        for ch in channels:
            if ch.get("channel_id") == channel_id:
                channel_info = ch
                break
        
        if not channel_info:
            await interaction.response.send_message(
                "❌ チャンネル情報が見つかりません。", 
                ephemeral=True
            )
            return

        # 通知モード選択画面を表示
        view = NotificationModeChoiceView(self.guild_id, channel_id, channel_info)
        
        current_mode = channel_info.get("notification_mode", "embed")
        mode_text = "Embedモード（詳細）" if current_mode == "embed" else "URLモード（軽量）"
        
        embed = discord.Embed(
            title="⚙️ 通知モードを選択",
            description=f"📺 **{channel_info.get('channel_name', channel_id)}** の通知モードを選択してください。",
            color=0x1E90FF
        )
        
        embed.add_field(
            name="� 現在の設定",
            value=f"**通知モード**: {mode_text}",
            inline=False
        )
        
        embed.add_field(
            name="� モード説明",
            value=(
                "**📝 Embedモード**: リッチな埋め込み形式で詳細情報を表示\n"
                "**🔗 URLモード**: 動画URLのみを送信（軽量・シンプル）\n"
                "**👥 ロールメンション**: URLモードではロールメンション可能"
            ),
            inline=False
        )
        
        embed.set_footer(text="⚙️ YouTube通知モード設定", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class NotificationModeChoiceView(discord.ui.View):
    """通知モード（Embed/URL）の選択画面"""
    def __init__(self, guild_id, channel_id, channel_info):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.channel_info = channel_info
        if debug:
            print(f"[DEBUG] NotificationModeChoiceView initialized: guild={guild_id}, channel={channel_id}")

    @discord.ui.button(label="📝 Embedモード", style=discord.ButtonStyle.primary, emoji="📝")
    async def embed_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if debug:
            print(f"[DEBUG] embed_mode button clicked by user={interaction.user.id}")
        
        await self.save_notification_mode("embed", interaction)

    @discord.ui.button(label="� URLモード", style=discord.ButtonStyle.secondary, emoji="�")
    async def url_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if debug:
            print(f"[DEBUG] url_mode button clicked by user={interaction.user.id}")
        
        # URLモードの場合、ロールメンション設定画面を表示
        view = RoleMentionView(self.guild_id, self.channel_id, self.channel_info)
        
        embed = discord.Embed(
            title="� ロールメンション設定",
            description=f"📺 **{self.channel_info.get('channel_name', self.channel_id)}** のURLモード通知でロールメンションを設定できます。",
            color=0x32CD32
        )
        
        current_role = self.channel_info.get("role_mention", "")
        if current_role:
            embed.add_field(
                name="📝 現在の設定",
                value=f"**ロールメンション**: <@&{current_role}>",
                inline=False
            )
        else:
            embed.add_field(
                name="� 現在の設定",
                value="**ロールメンション**: なし",
                inline=False
            )
        
        embed.add_field(
            name="💡 使用方法",
            value="ロールIDを入力するか、「なし」ボタンでメンションを無効化できます。",
            inline=False
        )
        
        embed.set_footer(text="� ロールメンション設定", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def save_notification_mode(self, mode, interaction):
        """通知モードを保存"""
        if debug:
            print(f"[DEBUG] save_notification_mode: guild={self.guild_id}, channel={self.channel_id}, mode={mode}")
        
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == self.channel_id:
                ch["notification_mode"] = mode
                # Embedモードの場合はロールメンションを削除
                if mode == "embed" and "role_mention" in ch:
                    del ch["role_mention"]
                channels[i] = ch
                break
        
        update_guild_data(self.guild_id, "youtube_channels", channels)
        
        mode_text = "Embedモード（詳細）" if mode == "embed" else "URLモード（軽量）"
        
        embed = discord.Embed(
            title="✅ 通知モードを保存しました",
            description=f"📺 **{self.channel_info.get('channel_name', self.channel_id)}** の通知モードを **{mode_text}** に設定しました。",
            color=0x32CD32
        )
        
        if mode == "embed":
            embed.add_field(
                name="📝 Embedモード特徴",
                value="リッチな埋め込み形式で動画情報、サムネイル、詳細データを表示します。",
                inline=False
            )
        else:
            embed.add_field(
                name="🔗 URLモード特徴", 
                value="動画URLのみを送信する軽量形式です。必要に応じてロールメンションも設定できます。",
                inline=False
            )
        
        embed.set_footer(text="⚙️ 通知モード設定完了", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RoleMentionView(discord.ui.View):
    """ロールメンション設定画面"""
    def __init__(self, guild_id, channel_id, channel_info):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.channel_info = channel_info
        if debug:
            print(f"[DEBUG] RoleMentionView initialized: guild={guild_id}, channel={channel_id}")

    @discord.ui.button(label="🔢 ロールID入力", style=discord.ButtonStyle.primary, emoji="🔢")
    async def role_input(self, interaction: discord.Interaction, button: discord.ui.Button):
        if debug:
            print(f"[DEBUG] role_input button clicked by user={interaction.user.id}")
        
        # ModalInputViewを使用してロールIDを入力
        view = ModalInputView(
            label="👥 ロールID設定",
            modal_title="👥 ロールメンション設定",
            text_label="ロールID",
            placeholder="メンションするロールのIDを入力してください",
            input_style="short",
            min_length=1,
            max_length=20,
            on_submit=self.save_role_mention,
            ephemeral=True
        )
        
        await interaction.response.send_message(
            "� **ロールIDを入力**\n\n"
            "メンションしたいロールのIDを入力してください。\n"
            "ロールIDの取得方法: 開発者モードを有効にして、ロールを右クリック → 「IDをコピー」",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="❌ メンションなし", style=discord.ButtonStyle.secondary, emoji="❌")
    async def no_mention(self, interaction: discord.Interaction, button: discord.ui.Button):
        if debug:
            print(f"[DEBUG] no_mention button clicked by user={interaction.user.id}")
        
        await self.save_url_mode_and_finish("", interaction)

    async def save_role_mention(self, interaction, value, recipient, view):
        """ロールメンションを保存してURLモード設定を完了"""
        # ロールIDの妥当性を簡易チェック
        try:
            role_id = int(value.strip())
            if role_id <= 0:
                raise ValueError("Invalid role ID")
        except ValueError:
            await interaction.response.send_message(
                "❌ 無効なロールIDです。数値のみを入力してください。",
                ephemeral=True
            )
            return
        
        await self.save_url_mode_and_finish(str(role_id), interaction)

    async def save_url_mode_and_finish(self, role_id, interaction):
        """URLモードとロールメンションを保存"""
        if debug:
            print(f"[DEBUG] save_url_mode_and_finish: guild={self.guild_id}, channel={self.channel_id}, role={role_id}")
        
        channels = get_guild_value(self.guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == self.channel_id:
                ch["notification_mode"] = "url"
                if role_id:
                    ch["role_mention"] = role_id
                else:
                    ch.pop("role_mention", None)
                channels[i] = ch
                break
        
        update_guild_data(self.guild_id, "youtube_channels", channels)
        
        embed = discord.Embed(
            title="✅ URLモード設定完了",
            description=f"� **{self.channel_info.get('channel_name', self.channel_id)}** をURLモードに設定しました。",
            color=0x32CD32
        )
        
        if role_id:
            embed.add_field(
                name="� ロールメンション",
                value=f"<@&{role_id}> をメンションします。",
                inline=False
            )
        else:
            embed.add_field(
                name="👥 ロールメンション",
                value="メンションは設定されていません。",
                inline=False
            )
        
        embed.add_field(
            name="🔗 URLモード特徴",
            value="動画URLのみを送信する軽量形式です。サーバーの負荷を最小限に抑えます。",
            inline=False
        )
        
        embed.set_footer(text="� URLモード設定完了", icon_url="https://youtube.com/favicon.ico")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


# --- YouTube通知チャンネル設定の互換性確保 ---
def migrate_youtube_channels(guild_id):
    """YouTube通知チャンネル設定に必要フィールドを追加（既存データとの互換性確保）"""
    channels = get_guild_value(guild_id, "youtube_channels", [])
    updated = False
    
    for i, channel_info in enumerate(channels):
        # last_live_statusフィールドの追加
        if "last_live_status" not in channel_info:
            channel_info["last_live_status"] = "none"  # デフォルト値
            updated = True
        
        # last_live_video_idフィールドの追加
        if "last_live_video_id" not in channel_info:
            channel_info["last_live_video_id"] = None  # デフォルト値
            updated = True
        
        # was_liveフィールドを新しい状態管理に対応
        current_live_status = channel_info.get("last_live_status", "none")
        expected_was_live = (current_live_status in ["live", "upcoming", "ended"])
        if channel_info.get("was_live") != expected_was_live:
            channel_info["was_live"] = expected_was_live
            updated = True
        
        # 通知モードフィールドの追加（デフォルトはembed）
        if "notification_mode" not in channel_info:
            channel_info["notification_mode"] = "embed"  # デフォルト値
            updated = True
        
        # カスタムメッセージ関連フィールドの削除（廃止機能）
        if "custom_video_message" in channel_info:
            del channel_info["custom_video_message"]
            updated = True
        
        if "custom_live_message" in channel_info:
            del channel_info["custom_live_message"]
            updated = True
        
        if updated:
            channels[i] = channel_info
    
    if updated:
        update_guild_data(guild_id, "youtube_channels", channels)
        if debug:
            print(f"[DEBUG] チャンネル設定マイグレーション完了: {guild_id}, 更新数: {len([ch for ch in channels if updated])}")
    
    return channels

def get_youtube_channels_with_migration(guild_id):
    """YouTube通知チャンネル設定を取得（自動的にlast_live_statusフィールドを追加）"""
    return migrate_youtube_channels(guild_id)


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
