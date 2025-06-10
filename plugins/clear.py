from discord.ext import commands
import discord
from discord import Embed, ButtonStyle, Interaction
from discord.ui import View, Button
from index import register_command, load_config, is_admin
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
                    deleted = await channel.purge(limit=100)
                    deleted_total += len(deleted)
                except Exception:
                    pass
            await interaction.response.send_message(f"🧹 全テキストチャンネルから合計{deleted_total}件のメッセージを削除しました", ephemeral=True)
            self.stop()

    @commands.command()
    async def clear(ctx, count: int = 10, mode: str = ""):
        """
        指定した件数だけメッセージを一括削除します（管理者専用）。
        例: #clear 10 → このチャンネルで直近10件削除
        例: #clear 100 all → 全チャンネルで最新100件ずつ削除
        例: #clear 10 day → このチャンネルの日付ごとに削除ボタンを表示
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
                "※管理者のみ利用可能"
            )
            embed = Embed(title="clearコマンドの使い方", description=usage, color=0x4ade80)
            await ctx.send(embed=embed)
            return
        if mode == "all":
            # 全チャンネルでcount件ずつ削除
            if count < 1 or count > 100:
                await ctx.send('1～100件の範囲で指定してください。')
                return
            deleted_total = 0
            for channel in ctx.guild.text_channels:
                try:
                    deleted = await channel.purge(limit=count)
                    deleted_total += len(deleted)
                except Exception:
                    pass
            await ctx.send(f'🧹 全テキストチャンネルから合計{deleted_total}件のメッセージを削除しました')
            return
        if mode == "day":
            # このチャンネルの実際のメッセージ日付ごと削除ボタン
            class ChannelDayClearView(View):
                def __init__(self, ctx, max_days=7, max_messages=500):
                    super().__init__(timeout=90)
                    self.ctx = ctx
                    self.author_id = ctx.author.id
                    self.channel = ctx.channel
                    # メッセージ履歴から日付を抽出
                    self.message_dates = []
                    self.max_days = max_days
                    self.max_messages = max_messages
                async def setup_items(self):
                    # 最新max_messages件から日付を抽出
                    unique_dates = set()
                    async for msg in self.channel.history(limit=self.max_messages):
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
                            deleted = await self.channel.purge(check=check)
                            deleted_total += len(deleted)
                        except Exception:
                            pass
                        await interaction.followup.send(f"🧹 {self.date_str} のメッセージをこのチャンネルから{deleted_total}件削除しました", ephemeral=True)
                        self.parent_view.stop()
            embed = Embed(title="日付指定一括削除", description="このチャンネル内の実際のメッセージ日付ごとに削除できます。\n\n⚠️ 注意: この操作は元に戻せません。", color=0xffa500)
            view = ChannelDayClearView(ctx)
            await view.setup_items()
            await ctx.send(embed=embed, view=view)
            return
        # 通常の件数指定削除（このチャンネルのみ）
        if count < 1 or count > 100:
            await ctx.send('1～100件の範囲で指定してください。')
            return
        deleted = await ctx.channel.purge(limit=count)
        await ctx.send(f'🧹 {len(deleted)}件のメッセージを削除しました', delete_after=3)
    register_command(bot, clear, aliases=None, admin=True)
