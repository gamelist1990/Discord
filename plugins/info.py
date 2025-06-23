import discord
from discord.ext import commands, tasks
import xml.etree.ElementTree as ET
import aiohttp
import asyncio
from datetime import datetime, timedelta
import json
import os
import re
from plugins import register_command
from DataBase import get_guild_value, update_guild_data


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

            rss_url = (
                f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            )

            # チェック間隔のバリデーション
            interval = int(self.check_interval.value or 30)
            if interval < 3:
                await interaction.response.send_message(
                    "❌ チェック間隔は最小3分です。", ephemeral=True
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
                rss_url,
                int(self.notification_channel.value),
                interval,
            )

            embed = discord.Embed(
                title="✅ 動画通知設定完了",
                description=f"チャンネルの動画通知が設定されました。",
                color=discord.Color.green(),
                timestamp=datetime.now(),
            )
            embed.add_field(
                name="チャンネルURL", value=self.channel_url.value, inline=False
            )
            embed.add_field(
                name="通知チャンネル",
                value=f"<#{self.notification_channel.value}>",
                inline=True,
            )
            embed.add_field(name="チェック間隔", value=f"{interval}分", inline=True)

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except ValueError:
            await interaction.response.send_message(
                "❌ チャンネルIDまたはチェック間隔が無効です。数値は3-60の範囲で入力してください。",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ エラーが発生しました: {str(e)}", ephemeral=True
            )

    async def extract_channel_id(self, url):
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

    async def save_notification_config(
        self, guild_id, channel_id, rss_url, notification_channel_id, interval
    ):
        """通知設定をDataBase.pyに保存"""
        channels = get_guild_value(guild_id, "youtube_channels", [])

        # 既存のチャンネルを更新するか新規追加
        found = False
        for ch in channels:
            if ch.get("channel_id") == channel_id:
                ch.update(
                    {
                        "channel_id": channel_id,
                        "rss_url": rss_url,
                        "notification_channel": notification_channel_id,
                        "interval": interval,
                        "last_video_id": None,
                        "was_live": False,
                        "created_at": datetime.now().isoformat(),
                    }
                )
                found = True
                break

        if not found:
            channels.append(
                {
                    "channel_id": channel_id,
                    "rss_url": rss_url,
                    "notification_channel": notification_channel_id,
                    "interval": interval,
                    "last_video_id": None,
                    "was_live": False,
                    "created_at": datetime.now().isoformat(),
                }
            )

        update_guild_data(guild_id, "youtube_channels", channels)


class VideoNotificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="📹 動画通知を設定", style=discord.ButtonStyle.primary, emoji="📹"
    )
    async def setup_notification(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        modal = VideoNotificationModal()
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="📋 設定一覧", style=discord.ButtonStyle.secondary, emoji="📋"
    )
    async def list_notifications(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
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

    async def create_notification_list_embed(self, guild_id):
        """設定一覧のEmbedを作成"""
        embed = discord.Embed(
            title="📋 動画通知設定一覧",
            color=discord.Color.blue(),
            timestamp=datetime.now(),
        )

        channels = get_guild_value(guild_id, "youtube_channels", [])

        if not channels:
            embed.description = "このサーバーには設定されている動画通知はありません。"
            return embed

        for channel_info in channels:
            status = (
                "🔴 ライブ中"
                if channel_info.get("was_live", False)
                else "⚫ オフライン"
            )
            embed.add_field(
                name=f"チャンネルID: {channel_info.get('channel_id', 'Unknown')} {status}",
                value=f"通知チャンネル: <#{channel_info.get('notification_channel', 'Unknown')}>\n"
                f"チェック間隔: {channel_info.get('interval', 30)}分\n"
                f"設定日時: {channel_info.get('created_at', 'N/A')}",
                inline=False,
            )

        return embed


class DeleteNotificationView(discord.ui.View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.select = self.create_delete_select()
        self.add_item(self.select)

    def create_delete_select(self):
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
            description=f"チャンネルID `{channel_id}` の動画通知設定を削除しました。",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class VideoNotificationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.checking = False
        self.loop_task = None
        self.request_cache = {}  # リクエストキャッシュ
        self.last_request_time = {}  # 最後のリクエスト時間
        self.min_request_interval = 60  # 同一チャンネルのリクエスト間隔（秒）

    @commands.Cog.listener()
    async def on_ready(self):
        """ボット起動時にチェックループを開始"""
        if not self.checking:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 動画通知システム開始")
            self.start_check_loop()

    def start_check_loop(self):
        """設定されたチェック間隔に基づくループを開始"""
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = self.bot.loop.create_task(self.notification_check_loop())

    async def notification_check_loop(self):
        """各チャンネルの設定されたチェック間隔に基づいて動画とライブ配信をチェックする統合ループ（レート制限対応）"""
        self.checking = True
        while True:
            try:
                await self.check_channels_by_interval()
                await asyncio.sleep(
                    60
                )  # 1分間隔でチェック（各チャンネルの間隔は個別管理）
            except Exception as e:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 通知ループエラー: {e}")
                await asyncio.sleep(60)

    async def check_channels_by_interval(self):
        """各チャンネルの設定されたチェック間隔に基づいてチェック（レート制限対応）"""
        current_time = datetime.now()

        # 全ギルドからチャンネルを収集し、チェック対象を決定
        channels_to_check = {}
        guild_channel_mapping = {}

        for guild in self.bot.guilds:
            channels = get_guild_value(guild.id, "youtube_channels", [])
            for channel_info in channels:
                channel_id = channel_info.get("channel_id")
                if not channel_id:
                    continue

                # 最後のチェック時間を確認
                last_check_str = channel_info.get("last_check")
                interval_minutes = channel_info.get("interval", 30)

                should_check = False

                if not last_check_str:
                    # 初回チェック
                    should_check = True
                    print(
                        f"[{current_time.strftime('%H:%M:%S')}] 初回チェック: {channel_id}"
                    )
                else:
                    try:
                        last_check_time = datetime.fromisoformat(last_check_str)
                        time_diff_minutes = (
                            current_time - last_check_time
                        ).total_seconds() / 60

                        if time_diff_minutes >= interval_minutes:
                            should_check = True
                            print(
                                f"[{current_time.strftime('%H:%M:%S')}] 間隔チェック対象: {channel_id} ({time_diff_minutes:.1f}分経過, 設定間隔: {interval_minutes}分)"
                            )
                    except (ValueError, TypeError):
                        # パースエラーの場合は強制チェック
                        should_check = True
                        print(
                            f"[{current_time.strftime('%H:%M:%S')}] 時間パースエラー、強制チェック: {channel_id}"
                        )

                if should_check:
                    if channel_id not in channels_to_check:
                        channels_to_check[channel_id] = channel_info
                        guild_channel_mapping[channel_id] = []
                    guild_channel_mapping[channel_id].append((guild, channel_info))

        # チェック対象のチャンネルを処理
        for channel_id, channel_info in channels_to_check.items():
            try:
                # レート制限チェック
                last_request_time = self.last_request_time.get(channel_id)

                if last_request_time:
                    request_time_diff = (
                        current_time - last_request_time
                    ).total_seconds()
                    if request_time_diff < self.min_request_interval:
                        print(
                            f"[{current_time.strftime('%H:%M:%S')}] レート制限スキップ: {channel_id}"
                        )
                        continue

                # キャッシュチェック
                cache_key = channel_id
                cache_time = 300  # 5分間キャッシュ

                if cache_key in self.request_cache:
                    cache_data, cache_timestamp = self.request_cache[cache_key]
                    if (current_time - cache_timestamp).total_seconds() < cache_time:
                        # キャッシュからデータを使用
                        await self.process_cached_data(
                            cache_data, guild_channel_mapping[channel_id]
                        )
                        # チェック時間を更新
                        self.update_last_check_time(guild_channel_mapping[channel_id])
                        continue

                # 新しいリクエストを実行
                xml_data = await self.fetch_channel_data_with_retry(channel_id)
                if xml_data:
                    # キャッシュに保存
                    self.request_cache[cache_key] = (xml_data, current_time)
                    self.last_request_time[channel_id] = current_time

                    # データを処理
                    await self.process_cached_data(
                        xml_data, guild_channel_mapping[channel_id]
                    )

                    # チェック時間を更新
                    self.update_last_check_time(guild_channel_mapping[channel_id])

                # リクエスト間隔を空ける
                await asyncio.sleep(2)  # 2秒間隔でリクエスト

            except Exception as e:
                print(
                    f"[{current_time.strftime('%H:%M:%S')}] チャンネル {channel_id} エラー: {e}"
                )

    def update_last_check_time(self, guild_channel_list):
        """最後のチェック時間を更新"""
        current_time = datetime.now()

        for guild, channel_info in guild_channel_list:
            channel_info["last_check"] = current_time.isoformat()

            # データベースに保存
            channels = get_guild_value(guild.id, "youtube_channels", [])
            for i, ch in enumerate(channels):
                if ch.get("channel_id") == channel_info.get("channel_id"):
                    channels[i] = channel_info
                    break
            update_guild_data(guild.id, "youtube_channels", channels)

    async def check_all_channels_with_rate_limit(self):
        """レート制限を考慮して全チャンネルをチェック"""
        # 全ギルドからチャンネルを収集し、重複を除去
        unique_channels = {}
        guild_channel_mapping = {}

        for guild in self.bot.guilds:
            channels = get_guild_value(guild.id, "youtube_channels", [])
            for channel_info in channels:
                channel_id = channel_info.get("channel_id")
                if channel_id:
                    if channel_id not in unique_channels:
                        unique_channels[channel_id] = channel_info
                        guild_channel_mapping[channel_id] = []
                    guild_channel_mapping[channel_id].append((guild, channel_info))

        # レート制限を考慮してチャンネルを順次チェック
        for channel_id, channel_info in unique_channels.items():
            try:
                # 最後のリクエストから十分な時間が経過しているかチェック
                current_time = datetime.now()
                last_time = self.last_request_time.get(channel_id)

                if last_time:
                    time_diff = (current_time - last_time).total_seconds()
                    if time_diff < self.min_request_interval:
                        print(
                            f"[{datetime.now().strftime('%H:%M:%S')}] レート制限: {channel_id} スキップ"
                        )
                        continue

                # キャッシュされたデータがあるかチェック
                cache_key = channel_id
                cache_time = 300  # 5分間キャッシュ

                if cache_key in self.request_cache:
                    cache_data, cache_timestamp = self.request_cache[cache_key]
                    if (current_time - cache_timestamp).total_seconds() < cache_time:
                        # キャッシュからデータを使用
                        await self.process_cached_data(
                            cache_data, guild_channel_mapping[channel_id]
                        )
                        continue

                # 新しいリクエストを実行
                xml_data = await self.fetch_channel_data_with_retry(channel_id)
                if xml_data:
                    # キャッシュに保存
                    self.request_cache[cache_key] = (xml_data, current_time)
                    self.last_request_time[channel_id] = current_time

                    # データを処理
                    await self.process_cached_data(
                        xml_data, guild_channel_mapping[channel_id]
                    )

                # リクエスト間隔を空ける
                await asyncio.sleep(2)  # 2秒間隔でリクエスト

            except Exception as e:
                print(
                    f"[{datetime.now().strftime('%H:%M:%S')}] チャンネル {channel_id} エラー: {e}"
                )

    async def fetch_channel_data_with_retry(self, channel_id, max_retries=3):
        """リトライ機能付きでチャンネルデータを取得"""
        for attempt in range(max_retries):
            try:
                if not self.session:
                    self.session = aiohttp.ClientSession()

                rss_url = (
                    f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                )

                async with self.session.get(rss_url) as response:
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

    async def process_cached_data(self, xml_data, guild_channel_list):
        """キャッシュされたXMLデータを処理"""
        try:
            entries = xml_data["entries"]
            if not entries:
                return

            current_time = datetime.now()

            for entry in entries:
                for guild, channel_info in guild_channel_list:
                    # 各チャンネルの設定された間隔に基づいて通知範囲を決定
                    interval_minutes = channel_info.get("interval", 30)
                    # 通知範囲をチェック間隔と同じに設定（最大でも間隔分さかのぼる）
                    notification_range = current_time - timedelta(
                        minutes=interval_minutes
                    )
                    await self.process_entry(
                        guild, channel_info, entry, notification_range
                    )

        except Exception as e:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] キャッシュデータ処理エラー: {e}"
            )

    async def check_all_channels(self):
        """従来のチェック方法（非推奨）"""
        # レート制限対応版を使用
        await self.check_all_channels_with_rate_limit()

    async def check_one_channel(self, guild, channel_info):
        """単一チャンネルの動画とライブ状態をチェック（レート制限対応）"""
        try:
            channel_id = channel_info.get("channel_id")
            if not channel_id:
                return

            # レート制限チェック
            current_time = datetime.now()
            last_time = self.last_request_time.get(channel_id)

            if last_time:
                time_diff = (current_time - last_time).total_seconds()
                if time_diff < self.min_request_interval:
                    return  # まだ間隔が短い

            # キャッシュチェック
            cache_key = channel_id
            if cache_key in self.request_cache:
                cache_data, cache_timestamp = self.request_cache[cache_key]
                if (
                    current_time - cache_timestamp
                ).total_seconds() < 300:  # 5分間キャッシュ
                    await self.process_cached_data(cache_data, [(guild, channel_info)])
                    return

            # 新しいデータを取得
            xml_data = await self.fetch_channel_data_with_retry(channel_id)
            if xml_data:
                self.request_cache[cache_key] = (xml_data, current_time)
                self.last_request_time[channel_id] = current_time
                await self.process_cached_data(xml_data, [(guild, channel_info)])

        except Exception as e:
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] チャンネルチェックエラー: {e}"
            )

    async def process_entry(self, guild, channel_info, entry, notification_cutoff_time):
        """エントリを処理（動画・ライブ両対応）"""
        try:
            # 基本情報を取得
            video_id_elem = entry.find(
                ".//{http://www.youtube.com/xml/schemas/2015}videoId"
            )
            if video_id_elem is None:
                return
            video_id = video_id_elem.text

            title_elem = entry.find(".//{http://www.w3.org/2005/Atom}title")
            author_elem = entry.find(
                ".//{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name"
            )
            published_elem = entry.find(".//{http://www.w3.org/2005/Atom}published")

            if not all([title_elem, author_elem, published_elem]):
                return

            title = title_elem.text
            author = author_elem.text
            published_str = published_elem.text

            # 投稿時間をパース
            try:
                if not published_str:
                    return
                published_dt_with_tz = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )
                published_dt = published_dt_with_tz.replace(tzinfo=None)
            except (ValueError, AttributeError):
                return

            # 設定された間隔内の投稿かチェック
            if published_dt < notification_cutoff_time:
                return

            # 既に処理済みかチェック
            if channel_info.get("last_video_id") == video_id:
                return

            # ライブ配信かどうかを判定
            is_live = await self.check_if_live(video_id)

            video_url = f"https://www.youtube.com/watch?v={video_id}"

            if is_live:
                # ライブ配信の場合
                was_live = channel_info.get("was_live", False)
                if not was_live:
                    await self.send_live_notification(
                        guild,
                        channel_info,
                        {
                            "title": title,
                            "author": author,
                            "url": video_url,
                            "published": published_str,
                            "video_id": video_id,
                        },
                    )
                    channel_info["was_live"] = True
                    self.update_channel_state(guild.id, channel_info, video_id)
            else:
                # 通常の動画投稿の場合
                await self.send_video_notification(
                    guild,
                    channel_info,
                    {
                        "title": title,
                        "author": author,
                        "url": video_url,
                        "published": published_str,
                        "video_id": video_id,
                    },
                )

                # ライブ状態をリセット
                if channel_info.get("was_live", False):
                    channel_info["was_live"] = False

                self.update_channel_state(guild.id, channel_info, video_id)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] エントリ処理エラー: {e}")

    async def check_if_live(self, video_id):
        """動画がライブ配信かどうかを判定（レート制限対応）"""
        try:
            # ライブ判定のキャッシュをチェック
            cache_key = f"live_{video_id}"
            current_time = datetime.now()

            if cache_key in self.request_cache:
                cache_result, cache_timestamp = self.request_cache[cache_key]
                if (
                    current_time - cache_timestamp
                ).total_seconds() < 180:  # 3分間キャッシュ
                    return cache_result

            if not self.session:
                self.session = aiohttp.ClientSession()

            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # タイムアウト設定でリクエスト時間を制限
            timeout = aiohttp.ClientTimeout(total=10)
            async with self.session.get(video_url, timeout=timeout) as response:
                if response.status != 200:
                    # エラー時はライブではないと判定
                    self.request_cache[cache_key] = (False, current_time)
                    return False

                content = await response.text()
                # ライブ配信の場合、HTMLに特定の文字列が含まれる
                is_live = (
                    '"isLive":true' in content
                    or '"isLiveContent":true' in content
                    or "hlsManifestUrl" in content
                )

                # 結果をキャッシュ
                self.request_cache[cache_key] = (is_live, current_time)

                # ライブ判定のリクエスト間隔を空ける
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
                title="🎬 新着動画通知",
                description=f"**{video_info['author']}** が新しい動画を投稿しました！",
                color=discord.Color.red(),
                timestamp=datetime.now(),
            )

            embed.add_field(
                name="📹 動画タイトル",
                value=f"[{video_info['title']}]({video_info['url']})",
                inline=False,
            )

            embed.add_field(
                name="👤 チャンネル", value=video_info["author"], inline=True
            )

            embed.add_field(name="📅 投稿時間", value=published_str, inline=True)

            # サムネイルを設定
            thumbnail_url = (
                f"https://img.youtube.com/vi/{video_info['video_id']}/maxresdefault.jpg"
            )
            embed.set_thumbnail(url=thumbnail_url)

            embed.set_footer(text="YouTube動画通知システム")

            await channel.send(embed=embed)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] 動画通知送信: {video_info['title']}"
            )

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

            embed = discord.Embed(
                title="🔴 ライブ配信開始！",
                description=f"**{video_info['author']}** がライブ配信を開始しました！",
                color=0xFF0000,
                timestamp=datetime.now(),
            )

            embed.add_field(
                name="📺 配信タイトル",
                value=f"[{video_info['title']}]({video_info['url']})",
                inline=False,
            )

            embed.add_field(
                name="👤 チャンネル", value=video_info["author"], inline=True
            )

            embed.add_field(
                name="🔗 配信を見る",
                value=f"[こちらから視聴]({video_info['url']})",
                inline=True,
            )

            # サムネイルを設定
            thumbnail_url = (
                f"https://img.youtube.com/vi/{video_info['video_id']}/maxresdefault.jpg"
            )
            embed.set_thumbnail(url=thumbnail_url)

            embed.set_footer(text="YouTubeライブ通知システム")

            await channel.send(embed=embed)
            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] ライブ通知送信: {video_info['title']}"
            )

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ライブ通知送信エラー: {e}")

    def update_channel_state(self, guild_id, channel_info, video_id=None):
        """チャンネルの状態を更新"""
        if video_id:
            channel_info["last_video_id"] = video_id
        channel_info["last_check"] = datetime.now().isoformat()

        channels = get_guild_value(guild_id, "youtube_channels", [])
        for i, ch in enumerate(channels):
            if ch.get("channel_id") == channel_info.get("channel_id"):
                channels[i] = channel_info
                break
        update_guild_data(guild_id, "youtube_channels", channels)

    async def cog_unload(self):
        """Cogアンロード時の処理"""
        self.checking = False
        if self.loop_task:
            self.loop_task.cancel()
        if self.session:
            await self.session.close()
        # キャッシュをクリア
        self.request_cache.clear()
        self.last_request_time.clear()


def setup(bot):
    # Cogを追加
    bot.add_cog(VideoNotificationCog(bot))

    # 通常のコマンドとして info を登録
    @commands.command()
    async def info(ctx):
        """
        動画通知機能の設定画面を表示します。
        YouTubeチャンネルの新着動画とライブ配信を設定されたチェック間隔でリアルタイム監視し、
        チェック間隔内に投稿された動画・開始された配信を通知します。
        """
        embed = discord.Embed(
            title="📹 動画・配信通知システム（ベータ版）",
            description="YouTubeチャンネルの新着動画とライブ配信を自動で通知するシステムです。\n"
            "XMLフィード（RSS）を使用してAPIを使わずに監視します。\n"
            "**設定されたチェック間隔でリアルタイム監視**を行い、投稿・配信開始を検知して通知します。",
            color=discord.Color.orange(),
            timestamp=datetime.now(),
        )

        embed.add_field(
            name="🔧 機能",
            value="• YouTubeチャンネルの新着動画通知\n"
            "• **🔴 ライブ配信開始通知（ベータ版）**\n"
            "• **設定されたチェック間隔でリアルタイム監視**\n"
            "• チェック間隔内に投稿・開始されたコンテンツを通知\n"
            "• 複数チャンネルの同時監視\n"
            "• XMLフィード活用（API不要）\n"
            "• DataBase.py統合管理",
            inline=False,
        )

        embed.add_field(
            name="📝 使用方法",
            value="1. **📹 動画通知を設定** をクリック\n"
            "2. YouTubeチャンネルURLを入力\n"
            "3. 通知先チャンネルIDを入力\n"
            "4. チェック間隔を設定（3-60分、デフォルト30分）",
            inline=False,
        )

        embed.add_field(
            name="⚙️ 対応URL形式",
            value="• `youtube.com/channel/UC...`\n"
            "• `youtube.com/c/チャンネル名`\n"
            "• `youtube.com/user/ユーザー名`\n"
            "• `youtube.com/@ハンドル名`",
            inline=False,
        )

        embed.add_field(
            name="⏰ 監視仕様",
            value="• **設定された間隔**でチェック実行\n"
            "• チェック間隔内に投稿・配信開始されたコンテンツを通知\n"
            "• 🎬 通常動画：赤色Embed\n"
            "• 🔴 ライブ配信：赤色Embed（ライブ専用デザイン）\n"
            "• **チェック間隔制限**：最小3分、最大60分（1時間）\n"
            "• **レート制限対策**：リクエストキャッシュ・間隔制御\n"
            "• リアルタイムに近い通知を実現",
            inline=False,
        )

        embed.add_field(
            name="🆕 ベータ機能",
            value="• ライブ配信検知機能\n"
            "• 配信状態の自動追跡\n"
            "• 配信開始・終了の状態管理",
            inline=False,
        )

        embed.set_footer(
            text="下のボタンから設定を開始してください | ベータ版機能を含みます"
        )

        view = VideoNotificationView()
        await ctx.send(embed=embed, view=view)

    register_command(bot, info, aliases=None, admin=True)
