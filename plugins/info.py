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
        if debug:
            print(f"[DEBUG] extract_channel_id: url={url}")

        """YouTubeチャンネルURLからチャンネルID（UC...）を抽出。/c/や/user/や/@はまずパターン、UCでなければHTMLから取得（og:url対応）"""
        import re
        import aiohttp

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
                # そうでなければHTMLからchannelIdまたはog:urlを抽出
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return None
                        html = await resp.text()
                        # 1. "channelId":"UCxxxx" を探す
                        m2 = re.search(r'"channelId":"(UC[^"]+)"', html)
                        if m2:
                            return m2.group(1)
                        # 2. <meta property="og:url" content="https://www.youtube.com/channel/UCxxxx"> を探す
                        m3 = re.search(
                            r'<meta property="og:url" content="https://www.youtube.com/channel/(UC[^"]+)">',
                            html,
                        )
                        if m3:
                            return m3.group(1)
                        return None
        return None

    async def extract_channel_name(self, channel_id):
        if debug:
            print(f"[DEBUG] extract_channel_name: channel_id={channel_id}")

        """YouTube APIを使わずにRSSフィードやHTMLからチャンネル名を取得"""
        # RSSフィードからチャンネル名を取得
        import aiohttp
        import xml.etree.ElementTree as ET
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(rss_url) as resp:
                    if resp.status == 200:
                        xml_content = await resp.text()
                        root = ET.fromstring(xml_content)
                        title_elem = root.find(".//{http://www.w3.org/2005/Atom}title")
                        if title_elem is not None:
                            return title_elem.text
        except Exception:
            pass
        return None

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
        self.session = None
        self.request_cache = {}
        self.last_request_time = {}
        self.min_request_interval = 60
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
        # RSSから最新動画情報を取得
        data = await self.fetch_channel_data_with_retry(channel_id)
        if not data or not data["entries"]:
            if debug:
                print(f"[DEBUG] RSS取得失敗または動画なし: {channel_id}")
            return
        latest_entry = data["entries"][0]
        video_id_elem = latest_entry.find("{http://www.youtube.com/xml/schemas/2015}videoId")
        if video_id_elem is None:
            if debug:
                print(f"[DEBUG] videoId要素なし: {channel_id}")
            return
        latest_video_id = video_id_elem.text
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
        # 動画情報をパース
        title_elem = latest_entry.find("{http://www.w3.org/2005/Atom}title")
        author_elem = latest_entry.find("{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name")
        published_elem = latest_entry.find("{http://www.w3.org/2005/Atom}published")
        video_url = f"https://www.youtube.com/watch?v={latest_video_id}"

        video_info = {
            "video_id": latest_video_id,
            "title": title_elem.text if title_elem is not None else "No Title",
            "author": author_elem.text if author_elem is not None else "Unknown",
            "published": published_elem.text if published_elem is not None else datetime.now(JST).isoformat(),
            "url": video_url,
        }

        # ライブ配信か判定
        is_live = await self.check_if_live(latest_video_id)
        if is_live:
            await self.send_live_notification(guild, channel_info, video_info)
        else:
            await self.send_video_notification(guild, channel_info, video_info)

        # 通知後、状態を更新
        self.update_channel_state(guild.id, channel_info, video_id=latest_video_id)
        if debug:
            print(f"[DEBUG] 新着動画通知済み: {latest_video_id}")

    async def fetch_channel_name(self, rss_url):
        if debug:
            print(f"[DEBUG] fetch_channel_name: rss_url={rss_url}")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(rss_url) as resp:
                    if resp.status == 200:
                        xml = await resp.text()
                        root = ET.fromstring(xml)
                        title_elem = root.find(".//{http://www.w3.org/2005/Atom}title")
                        if title_elem is not None:
                            return title_elem.text
        except Exception as e:
            print(f"[VideoNotificationHandler] チャンネル名取得失敗: {e}")
        return None

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
        if debug:
            print(f"[DEBUG] fetch_channel_data_with_retry: channel_id={channel_id}")
        for attempt in range(max_retries):
            try:
                rss_url = (
                    f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.get(rss_url) as response:
                        if response.status == 200:
                            xml_content = await response.text()
                            root = ET.fromstring(xml_content)
                            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
                            return {
                                "xml_content": xml_content,
                                "entries": entries,
                                "channel_id": channel_id,
                            }
                        elif response.status == 429:  # Too Many Requests
                            wait_time = 60 * (attempt + 1)  # 指数バックオフ
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] レート制限検出: {wait_time}秒待機"
                            )
                            await asyncio.sleep(wait_time)
                        else:
                            print(
                                f"[{datetime.now().strftime('%H:%M:%S')}] HTTP {response.status}: {channel_id}"
                            )
                            return None
            except Exception as e:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] リクエストエラー (試行 {attempt + 1}): {e}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(5 * (attempt + 1))
        return None

    async def check_if_live(self, video_id):
        if debug:
            print(f"[DEBUG] check_if_live: video_id={video_id}")
        try:
            # キャッシュを使わず毎回リクエスト
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
                    await asyncio.sleep(1)
                    return is_live
        except asyncio.TimeoutError:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] ライブ判定タイムアウト: {video_id}"
            )
            return False
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ライブ判定エラー: {e}")
            return False

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

            # 公開時間をフォーマット
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
                name="� 配信状態", 
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
        name="� 主要機能",
        value="```diff\n"
        "+ YouTubeチャンネルの新着動画通知\n"
        "+ 🔴 ライブ配信開始通知（ベータ版）\n"
        "+ リアルタイム監視システム\n"
        "+ 複数チャンネル同時監視\n"
        "+ XMLフィード活用（API不要）\n"
        "+ 高度な状態管理\n"
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
        name="🆕 ベータ機能",
        value="```\n"
        "🔴 ライブ配信検知\n"
        "📊 配信状態追跡\n"
        "🔄 リアルタイム状態管理\n"
        "⚡ 即座に通知\n"
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
