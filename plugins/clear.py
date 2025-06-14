from discord.ext import commands
import discord
from discord import Embed, ButtonStyle, Interaction
from discord.ui import View, Button
from plugins import register_command
from index import load_config, is_admin
import asyncio
from datetime import datetime, timedelta, timezone

# 管理者専用: メッセージ一括削除コマンド

# --- サーバーごとの削除タスク管理 ---
clear_tasks = {}

# --- 14日以内のメッセージはbulk delete、古いものは個別delete ---
async def efficient_delete(channel, user_id=None, count=10, on_progress=None, cancel_event=None):
    deleted = 0
    now = datetime.now(timezone.utc)
    fourteen_days_ago = now - timedelta(days=14)
    messages = []
    async for msg in channel.history(limit=500):
        if user_id is not None and msg.author.id != user_id:
            continue
        messages.append(msg)
        if len(messages) >= count:
            break
    # 14日以内
    recent_msgs = [m for m in messages if m.created_at > fourteen_days_ago]
    # 14日より前
    old_msgs = [m for m in messages if m.created_at <= fourteen_days_ago]
    if recent_msgs:
        try:
            purged = await channel.purge(limit=len(recent_msgs), check=(lambda m: m in recent_msgs), bulk=True)
            deleted += len(purged)
            if on_progress:
                await on_progress(f"🧹 14日以内の{len(purged)}件をまとめて削除")
        except Exception as e:
            if on_progress:
                await on_progress(f"purge失敗: {e}")
    # 古いものは個別delete
    for m in old_msgs:
        if cancel_event and cancel_event.is_set():
            break
        try:
            await m.delete()
            deleted += 1
            if on_progress and deleted % 10 == 0:
                await on_progress(f"進捗: {deleted}件削除済み")
        except Exception:
            pass
    return deleted

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
        async def safe_bulk_delete(messages, interval=0.6, batch_size=3, max_retries=3):
            """
            メッセージリストをbatch_size件ずつ並列で削除し、バッチごとにinterval秒待機（Discordレートリミット対策＆高速化）
            レート制限(429)時は自動リトライし、リトライ時はintervalを延長
            """
            import asyncio
            import time
            deleted_count = 0
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i+batch_size]
                retries = 0
                while retries <= max_retries:
                    tasks = [msg.delete() for msg in batch]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    # レート制限エラーがあればリトライ
                    rate_limited = any(getattr(r, 'status', None) == 429 for r in results if isinstance(r, Exception))
                    deleted_count += sum(1 for r in results if not isinstance(r, Exception))
                    if not rate_limited:
                        break
                    # レート制限時はintervalを延長してリトライ
                    retries += 1
                    await asyncio.sleep(interval * (retries + 1))
                await asyncio.sleep(interval)
            return deleted_count

    @commands.command()
    async def clear(ctx, count: str = "10", mode: str = ""):
        """
        指定した件数だけメッセージを一括削除します（管理者専用）。
        例: #clear 10 → このチャンネルで直近10件削除
        例: #clear 100 all → 全チャンネルで最新100件ずつ削除
        例: #clear 10 day → このチャンネルの日付ごとに削除ボタンを表示
        例: #clear 100 user <id> → 指定ユーザーのメッセージを最大100件削除
        例: #clear stop → 進行中の削除タスクをキャンセル

        ・14日以内のメッセージは高速一括削除（bulk delete/purge）
        ・14日より前のメッセージは個別削除
        ・サーバーごとに同時に1つだけ削除タスクが実行されます
        ・#clear stop で進行中の削除タスクをキャンセル可能
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
                "・#clear 100 user <id> → 指定ユーザーのメッセージを最大100件削除\n"
                "・#clear stop → 進行中の削除タスクをキャンセル\n"
                "※管理者のみ利用可能\n"
                "\n14日以内のメッセージは高速一括削除（bulk delete/purge）、14日より前は個別削除。\n同時に複数の削除タスクは実行されません。"
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
        guild_id = ctx.guild.id
        # --- #clear stop でキャンセル ---
        if count == "stop":
            task = clear_tasks.get(guild_id)
            if task and not task.done():
                task.cancel()
                await ctx.send("🛑 進行中の削除タスクをキャンセルしました")
            else:
                await ctx.send("現在進行中の削除タスクはありません")
            return
        # --- 多重実行防止 ---
        if guild_id in clear_tasks and not clear_tasks[guild_id].done():
            await ctx.send("⚠️ 既に進行中の削除タスクがあります。#clear stop でキャンセルできます")
            return
        # --- 削除タスク本体 ---
        async def do_clear():
            try:
                # --- ユーザー指定削除: #clear 100 user <id> ---
                if mode == "user" or (len(mode) == 0 and len(ctx.message.content.strip().split()) >= 4 and ctx.message.content.strip().split()[2] == "user"):
                    # 例: #clear 100 user 123456789012345678
                    args = ctx.message.content.strip().split()
                    # args[0]=#clear, args[1]=count, args[2]=user, args[3]=id
                    if len(args) >= 4 and args[2] == "user":
                        try:
                            user_id = int(args[3])
                        except Exception:
                            await ctx.send("ユーザーIDが不正です。", delete_after=3)
                            return
                        if count_int < 1 or count_int > 100:
                            await ctx.send('1～100件の範囲で指定してください。')
                            return
                        channel = ctx.channel
                        cancel_event = asyncio.Event()
                        clear_tasks[guild_id] = asyncio.current_task()
                        deleted = await efficient_delete(channel, user_id=user_id, count=count_int, cancel_event=cancel_event)
                        await ctx.send(f'🧹 ユーザー <@{user_id}> のメッセージ{deleted}件を削除しました', delete_after=3)
                        ClearRateLimitHelper.reset_user(ctx)
                        return
                if mode == "all":
                    # 全チャンネルでcount件ずつ削除
                    if count_int < 1 or count_int > 100:
                        await ctx.send('1～100件の範囲で指定してください。')
                        return
                    deleted_total = 0
                    cancel_event = asyncio.Event()
                    clear_tasks[guild_id] = asyncio.current_task()
                    for channel in ctx.guild.text_channels:
                        deleted_total += await efficient_delete(channel, count=count_int, cancel_event=cancel_event)
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
                # 通常の件数指定削除（このチャンネルのみ）
                if count_int < 1 or count_int > 100:
                    await ctx.send('1～100件の範囲で指定してください。')
                    return
                channel = ctx.channel
                cancel_event = asyncio.Event()
                clear_tasks[guild_id] = asyncio.current_task()
                deleted = await efficient_delete(channel, count=count_int, cancel_event=cancel_event)
                await ctx.send(f'🧹 {deleted}件のメッセージを削除しました', delete_after=3)
                ClearRateLimitHelper.reset_user(ctx)
            except asyncio.CancelledError:
                await ctx.send("🛑 削除タスクがキャンセルされました")
            finally:
                if guild_id in clear_tasks:
                    del clear_tasks[guild_id]
        # タスクとして実行
        task = asyncio.create_task(do_clear())
        clear_tasks[guild_id] = task

    register_command(bot, clear, aliases=None, admin=True)
