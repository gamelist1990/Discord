from discord.ext import commands
import discord
from discord import Embed, ButtonStyle, Interaction
from discord.ui import View, Button
from plugins import register_command
from index import load_config, is_admin
from datetime import datetime, timedelta

# 管理者専用: メッセージ一括削除コマンド

def setup(bot):
    class AllClearView(View):
        def __init__(self, ctx):
            super().__init__(timeout=60)
            self.ctx = ctx
            self.author_id = ctx.author.id

        @discord.ui.button(label="全チャンネル100件削除", style=ButtonStyle.danger)
        async def all_clear(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ あなたはこの操作を実行できません。", ephemeral=True)
                return
            guild = interaction.guild or self.ctx.guild
            deleted_total = 0
            for channel in guild.text_channels:
                try:
                    # botのメッセージも含めて全て削除（checkは常にTrueを返す関数を指定）
                    deleted = await channel.purge(limit=100, check=lambda m: True)
                    deleted_total += len(deleted)
                except Exception:
                    pass
            await interaction.response.send_message(f"🧹 全テキストチャンネルから合計{deleted_total}件のメッセージを削除しました", ephemeral=True)
            self.stop()

    class ClearRateLimitHelper:
        """
        clearコマンド専用のレート制限解除・回避・安全削除ヘルパー
        """
        @staticmethod
        def reset_user(ctx):
            try:
                from index import rate_limited_users, user_command_timestamps
                user_id = str(ctx.author.id)
                if user_id in rate_limited_users:
                    del rate_limited_users[user_id]
                if user_id in user_command_timestamps:
                    user_command_timestamps[user_id].clear()
            except Exception:
                pass

        @staticmethod
        async def safe_bulk_delete(messages, interval=0.6):
            """
            メッセージリストを1件ずつinterval秒間隔で削除（Discordレートリミット対策）
            botのメッセージも含めて削除
            """
            import asyncio
            deleted_count = 0
            for msg in messages:
                try:
                    await msg.delete()
                    deleted_count += 1
                    await asyncio.sleep(interval)
                except Exception:
                    pass
            return deleted_count

    @commands.command()
    async def clear(ctx, count: str = "10", mode: str = ""):
        """
        指定した件数だけメッセージを一括削除します（管理者専用）。
        例: #clear 10 → このチャンネルで直近10件削除
        例: #clear 100 all → 全チャンネルで最新100件ずつ削除
        例: #clear 10 day → このチャンネルの日付ごとに削除ボタンを表示
        例: #clear arasi → このチャンネル内の荒らし（類似）メッセージを一括削除
        
        """
        config = load_config()
        if not is_admin(str(ctx.author.id), ctx.guild.id, config):
            await ctx.send('❌ あなたは管理者権限を持っていません。')
            return
        # #clear だけの場合は使い方を表示
        if ctx.invoked_with == "clear" and ctx.invoked_subcommand is None and ctx.message.content.strip() == f"{ctx.prefix}clear":
            usage = (
                "【clearコマンドの使い方】\n"
                "・#clear 10 → このチャンネルで直近10件削除\n"
                "・#clear 100 all → 全チャンネルで最新100件ずつ削除\n"
                "・#clear 10 day → このチャンネルの日付ごとに削除ボタンを表示\n"
                "・#clear arasi → このチャンネル内の荒らし（類似）メッセージを一括削除\n"
                "※管理者のみ利用可能"
            )
            embed = Embed(title="clearコマンドの使い方", description=usage, color=0x4ade80)
            await ctx.send(embed=embed)
            return
        # countが数字でなければmodeとして扱う
        if count.isdigit():
            count_int = int(count)
        else:
            mode = count
            count_int = 10
        # arasiモードの最大件数制限
        if mode == "arasi":
            if count_int > 100:
                count_int = 100  # 明示的な数指定時は最大100
            elif count == "arasi" or count_int > 20:
                count_int = 20  # デフォルトや #clear arasi のみは最大20
        if mode == "all":
            # 全チャンネルでcount件ずつ削除
            if count_int < 1 or count_int > 100:
                await ctx.send('1～100件の範囲で指定してください。')
                return
            deleted_total = 0
            for channel in ctx.guild.text_channels:
                messages = [msg async for msg in channel.history(limit=count_int)]
                deleted_total += await ClearRateLimitHelper.safe_bulk_delete(messages)
            await ctx.send(f'🧹 全テキストチャンネルから合計{deleted_total}件のメッセージを削除しました')
            ClearRateLimitHelper.reset_user(ctx)
            return
        if mode == "day":
            # このチャンネルの実際のメッセージ日付ごと削除ボタン
            class ChannelDayClearView(View):
                def __init__(self, ctx, max_days=7, max_messages=500):
                    super().__init__(timeout=90)
                    self.ctx = ctx
                    self.author_id = ctx.author.id
                    self.channel = ctx.channel
                    self.message_dates = []
                    self.max_days = max_days
                    self.max_messages = max_messages
                async def setup_items(self):
                    # 実際に削除可能なメッセージの日付のみ抽出
                    unique_dates = set()
                    guild = self.channel.guild
                    me = guild.me if guild else None
                    async for msg in self.channel.history(limit=self.max_messages):
                        # Botが削除できるメッセージのみ対象
                        if me and (msg.author == me or self.channel.permissions_for(me).manage_messages):
                            unique_dates.add(msg.created_at.date())
                            if len(unique_dates) >= self.max_days:
                                break
                    # 新しい順に並べてボタン追加
                    for day in sorted(unique_dates, reverse=True):
                        date_str = day.strftime("%Y/%m/%d")
                        self.add_item(self.DayButton(date_str, self.author_id, self, self.channel))
                class DayButton(Button):
                    def __init__(self, date_str, author_id, parent_view, channel):
                        super().__init__(label=date_str, style=ButtonStyle.primary)
                        self.date_str = date_str
                        self.author_id = author_id
                        self.parent_view = parent_view
                        self.channel = channel
                    async def callback(self, interaction: Interaction):
                        if interaction.user.id != self.author_id:
                            await interaction.response.send_message("❌ あなたはこの操作を実行できません。", ephemeral=True)
                            return
                        await interaction.response.defer(ephemeral=True)
                        try:
                            target_date = datetime.strptime(self.date_str, "%Y/%m/%d")
                        except Exception:
                            await interaction.followup.send("日付形式が不正です。", ephemeral=True)
                            return
                        deleted_total = 0
                        def check(m):
                            return m.created_at.date() == target_date.date()
                        try:
                            messages = [m async for m in self.channel.history(limit=500) if check(m)]
                            deleted_total += await ClearRateLimitHelper.safe_bulk_delete(messages)
                        except Exception:
                            pass
                        await interaction.followup.send(f"🧹 {self.date_str} のメッセージをこのチャンネルから{deleted_total}件削除しました", ephemeral=True)
                        self.parent_view.stop()
            embed = Embed(title="日付指定一括削除", description="このチャンネル内の実際のメッセージ日付ごとに削除できます。\n\n⚠️ 注意: この操作は元に戻せません。", color=0xffa500)
            view = ChannelDayClearView(ctx)
            await view.setup_items()
            await ctx.send(embed=embed, view=view)
            ClearRateLimitHelper.reset_user(ctx)
            return
        if mode == "arasi":
            # 荒らしメッセージ（類似性の高いメッセージ or 画像スパム）をこのチャンネルのみで削除
            import difflib
            threshold = 0.85  # 類似度のしきい値（調整可）
            max_messages = count_int  # 指定件数まで
            deleted_total = 0
            channel = ctx.channel
            messages = [msg async for msg in channel.history(limit=max_messages)]
            to_delete = set()
            # テキスト類似スパム
            for i, msg in enumerate(messages):
                if not msg.content or msg.id in to_delete:
                    continue
                for j in range(i+1, len(messages)):
                    other = messages[j]
                    if not other.content or other.id in to_delete:
                        continue
                    ratio = difflib.SequenceMatcher(None, msg.content, other.content).ratio()
                    if ratio >= threshold:
                        to_delete.add(msg.id)
                        to_delete.add(other.id)
            # 画像・動画スパム
            media_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".mp4", ".mov", ".avi", ".wmv", ".webm", ".mkv")
            for msg in messages:
                if any(att.filename.lower().endswith(ext) for att in getattr(msg, 'attachments', []) for ext in media_exts):
                    to_delete.add(msg.id)
            if to_delete:
                target_msgs = [msg for msg in messages if msg.id in to_delete]
                deleted_total += await ClearRateLimitHelper.safe_bulk_delete(target_msgs)
            await ctx.send(f'🧹 このチャンネル内の類似性の高い荒らしメッセージ・画像/動画スパムを合計{deleted_total}件削除しました')
            ClearRateLimitHelper.reset_user(ctx)
            return
        # 通常の件数指定削除（このチャンネルのみ）
        if count_int < 1 or count_int > 100:
            await ctx.send('1～100件の範囲で指定してください。')
            return
        messages = [msg async for msg in ctx.channel.history(limit=count_int)]
        deleted = await ClearRateLimitHelper.safe_bulk_delete(messages)
        await ctx.send(f'🧹 {deleted}件のメッセージを削除しました', delete_after=3)
        ClearRateLimitHelper.reset_user(ctx)
    register_command(bot, clear, aliases=None, admin=True)
