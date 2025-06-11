from discord.ext import commands, tasks
from plugins import register_command
from plugins.common_ui import ModalInputView
import discord
import asyncio
import re
from index import load_config, is_admin
from datetime import datetime, timedelta

# 臨時DM管理用カテゴリ名
DM_CATEGORY_NAME = "📥｜ DM"


# ユーザー検索用関数
async def search_members(ctx, query):
    query = query.strip().lower()
    results = []
    for m in ctx.guild.members:
        if (
            query in m.name.lower()
            or query in m.display_name.lower()
            or query == str(m.id)
        ):
            results.append(m)
    return results


# 臨時DMカテゴリ取得/作成
async def get_or_create_dm_category(guild):
    for cat in guild.categories:
        if cat.name == DM_CATEGORY_NAME:
            return cat
    overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False)}
    return await guild.create_category(DM_CATEGORY_NAME, overwrites=overwrites)


# 権限設定（edit.pyの外部アプリコマンド無効化を参考）
async def set_external_app_commands_permission(channel, member):
    overwrite = channel.overwrites_for(member)
    overwrite.use_external_apps = False
    await channel.set_permissions(
        member, overwrite=overwrite, reason="臨時DM: 外部アプリコマンド無効化"
    )


# DMカテゴリ内でユーザーが関与するDMチャンネル数をカウント
async def count_user_dm_channels(guild, user):
    cat = await get_or_create_dm_category(guild)
    count = 0
    for ch in cat.text_channels:
        if ch.topic and str(user.id) in ch.topic:
            count += 1
    return count


# topicからDMユーザーID2つを抽出
DM_TOPIC_PATTERN = re.compile(r"臨時DM: (\d+) <-> (\d+)")


def extract_dm_user_ids(topic):
    if not topic:
        return None, None
    m = DM_TOPIC_PATTERN.search(topic)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


# --- DM自動削除ループ ---
@tasks.loop(minutes=5)
async def auto_delete_expired_dm_channels_task(bot):
    try:
        now = datetime.utcnow()
        for guild in bot.guilds:
            cat = None
            for c in guild.categories:
                if c.name == DM_CATEGORY_NAME:
                    cat = c
                    break
            if not cat:
                continue
            for ch in list(cat.text_channels):
                # topicから作成時刻を抽出
                if ch.topic and ch.topic.startswith("臨時DM: "):
                    # topic例: "臨時DM: <author_id> <-> <target_id> | created: <timestamp>"
                    parts = ch.topic.split("| created: ")
                    if len(parts) == 2:
                        try:
                            created_at = datetime.fromisoformat(parts[1].strip())
                        except Exception:
                            continue
                        if now - created_at > timedelta(hours=1):
                            try:
                                await ch.delete(reason="臨時DM: 1時間経過による自動削除")
                            except Exception as e:
                                print(f"[DM自動削除] 削除失敗: {e}")
    except Exception as e:
        print(f"[DM自動削除] ループ例外: {e}")


# 臨時DMコマンド


def setup(bot):
    @commands.command()
    async def dm(ctx, *, query=None):
        """
        #dm ...臨時DM UIを表示
        #dm close ...このDMチャンネルを閉じる
        #dm close all ...管理者:臨時DM全削除
        """
        if query is None:
            # まず「DM UIを開く」ボタンを表示
            embed = discord.Embed(
                title="臨時DM UI",
                description="下のボタンから操作を開始してください",
                color=0x4ADE80,
                
            )

            async def on_dm_ui_button(interaction, view):
                # あなたへのメッセージで2択ボタンを表示
                embed2 = discord.Embed(
                    title="臨時DM開設",
                    description="どちらの方法で相手を指定しますか？",
                    color=0x4ADE80,
                )

                class DmChoiceView(discord.ui.View):
                    def __init__(self, ctx):
                        super().__init__(timeout=60)
                        self.ctx = ctx

                    @discord.ui.button(
                        label="ユーザー検索", style=discord.ButtonStyle.primary
                    )
                    async def search_btn(self, interaction2, button):
                        # 検索モーダルを表示
                        class SearchModal(discord.ui.Modal, title="ユーザー検索"):
                            search_word = discord.ui.TextInput(
                                label="ユーザー名/ID",
                                placeholder="例: ユーザー名やID",
                                required=True,
                            )

                            async def on_submit(self, interaction3):
                                await interaction3.response.defer(ephemeral=True)
                                members = await search_members(
                                    ctx, self.search_word.value
                                )
                                if not members:
                                    await interaction3.followup.send(
                                        "❌ 該当ユーザーが見つかりません",
                                        ephemeral=True,
                                    )
                                    return
                                if len(members) == 1:
                                    target = members[0]
                                    # 確認Embed＋はい/いいえView
                                    embed = discord.Embed(
                                        title="DM開始確認",
                                        description=f"このユーザーとDMを開始しますか？\n\n{target.mention}",
                                        color=0x4ADE80,
                                    )

                                    class ConfirmView(discord.ui.View):
                                        def __init__(self):
                                            super().__init__(timeout=30)

                                        @discord.ui.button(
                                            label="はい",
                                            style=discord.ButtonStyle.success,
                                        )
                                        async def yes(self, i, b):
                                            await i.response.defer(ephemeral=True)
                                            await create_dm_channel(
                                                ctx, ctx.author, target, i
                                            )
                                            try:
                                                await i.message.delete()
                                            except discord.NotFound:
                                                pass
                                            self.stop()

                                        @discord.ui.button(
                                            label="いいえ",
                                            style=discord.ButtonStyle.danger,
                                        )
                                        async def no(self, i, b):
                                            await i.response.send_message(
                                                "キャンセルしました", ephemeral=True
                                            )
                                            try:
                                                await i.message.delete()
                                            except discord.NotFound:
                                                pass
                                            self.stop()

                                    await interaction3.followup.send(
                                        embed=embed, view=ConfirmView(), ephemeral=True
                                    )
                                    return
                                # 複数候補: Embedリスト＋Select
                                desc = (
                                    "候補が複数見つかりました。選択してください。\n\n"
                                )
                                options = []
                                for m in members[:25]:
                                    desc += f"- {m.mention} ({m.name}#{m.discriminator} / {m.id})\n"
                                    options.append(
                                        discord.SelectOption(
                                            label=f"{m.display_name} ({m.name})",
                                            value=str(m.id),
                                        )
                                    )
                                embed = discord.Embed(
                                    title="ユーザー候補リスト",
                                    description=desc,
                                    color=0xFBBF24,
                                )

                                class MemberSelect(discord.ui.Select):
                                    def __init__(self):
                                        super().__init__(
                                            placeholder="ユーザーを選択...",
                                            options=options,
                                        )

                                    async def callback(self, interaction):
                                        target_id = int(self.values[0])
                                        target = ctx.guild.get_member(target_id)
                                        # 確認Embed＋はい/いいえView
                                        embed2 = discord.Embed(
                                            title="DM開始確認",
                                            description=f"このユーザーとDMを開始しますか？\n\n{target.mention}",
                                            color=0x4ADE80,
                                        )

                                        class ConfirmView(discord.ui.View):
                                            def __init__(self):
                                                super().__init__(timeout=30)

                                            @discord.ui.button(
                                                label="はい",
                                                style=discord.ButtonStyle.success,
                                            )
                                            async def yes(self, i, b):
                                                await i.response.defer(ephemeral=True)
                                                await create_dm_channel(
                                                    ctx, ctx.author, target, i
                                                )
                                                try:
                                                    await i.message.delete()
                                                except discord.NotFound:
                                                    pass
                                                self.stop()

                                            @discord.ui.button(
                                                label="いいえ",
                                                style=discord.ButtonStyle.danger,
                                            )
                                            async def no(self, i, b):
                                                await i.response.send_message(
                                                    "キャンセルしました", ephemeral=True
                                                )
                                                try:
                                                    await i.message.delete()
                                                except discord.NotFound:
                                                    pass
                                                self.stop()

                                        await interaction.response.send_message(
                                            embed=embed2,
                                            view=ConfirmView(),
                                            ephemeral=True,
                                        )

                                view = discord.ui.View(timeout=60)
                                view.add_item(MemberSelect())
                                await interaction3.followup.send(
                                    embed=embed, view=view, ephemeral=True
                                )

                        await interaction2.response.send_modal(SearchModal())

                    @discord.ui.button(
                        label="ユーザー選択", style=discord.ButtonStyle.secondary
                    )
                    async def select_btn(self, interaction2, button):
                        # オンライン・アクティブなユーザーSelectを表示（idle/dnd含む）
                        online_statuses = [discord.Status.online, discord.Status.idle, discord.Status.dnd]
                        online_members = [
                            m for m in ctx.guild.members
                            if (getattr(m, 'status', None) in online_statuses) and not m.bot and m != ctx.author
                        ]
                        # Fallback: オンライン0人なら全メンバーからbot/自分以外を候補に
                        if not online_members:
                            online_members = [
                                m for m in ctx.guild.members
                                if not m.bot and m != ctx.author
                            ]
                            if not online_members:
                                await interaction2.response.send_message(
                                    "❌ 選択可能なユーザーがいません", ephemeral=True
                                )
                                return
                            info = "（全メンバーから選択）"
                        else:
                            info = ""
                        options = [
                            discord.SelectOption(
                                label=f"{m.display_name} ({m.name})", value=str(m.id)
                            )
                            for m in online_members[:25]
                        ]

                        class UserSelect(discord.ui.Select):
                            def __init__(self):
                                super().__init__(
                                    placeholder="DM相手を選択...", options=options
                                )

                            async def callback(self, interaction):
                                target_id = int(self.values[0])
                                target = ctx.guild.get_member(target_id)
                                # 確認Embed＋はい/いいえView
                                embed = discord.Embed(
                                    title="DM開始確認",
                                    description=f"このユーザーとDMを開始しますか？\n\n{target.mention}",
                                    color=0x4ADE80,
                                )

                                class ConfirmView(discord.ui.View):
                                    def __init__(self):
                                        super().__init__(timeout=30)

                                    @discord.ui.button(
                                        label="はい", style=discord.ButtonStyle.success
                                    )
                                    async def yes(self, i, b):
                                        await i.response.defer(ephemeral=True)
                                        await create_dm_channel(
                                            ctx, ctx.author, target, i
                                        )
                                        try:
                                            await i.message.delete()
                                        except discord.NotFound:
                                            pass
                                        self.stop()

                                    @discord.ui.button(
                                        label="いいえ", style=discord.ButtonStyle.danger
                                    )
                                    async def no(self, i, b):
                                        await i.response.send_message(
                                            "キャンセルしました", ephemeral=True
                                        )
                                        try:
                                            await i.message.delete()
                                        except discord.NotFound:
                                            pass
                                        self.stop()

                                await interaction.response.send_message(
                                    embed=embed, view=ConfirmView(), ephemeral=True
                                )

                        view2 = discord.ui.View(timeout=60)
                        view2.add_item(UserSelect())
                        await interaction2.response.send_message(
                            f"DM相手を選択してください {info}",
                            view=view2,
                            ephemeral=True,
                        )

                # --- ここから共通確認UI ---
                async def show_dm_confirm(ctx, interaction, target):
                    # DM作成数制限チェック
                    user_dm_count = await count_user_dm_channels(ctx.guild, ctx.author)
                    if user_dm_count >= 2:
                        await interaction.followup.send(
                            "❌ あなたが作成できる臨時DMチャンネルは2個までです",
                            ephemeral=True,
                        )
                        return
                    embed = discord.Embed(
                        title="DM開始確認",
                        description=f"このユーザーとDMを開始しますか？\n\n{target.mention}",
                        color=0x4ADE80,
                    )

                    class ConfirmView(discord.ui.View):
                        def __init__(self):
                            super().__init__(timeout=30)
                            self.value = None

                        @discord.ui.button(
                            label="はい", style=discord.ButtonStyle.success
                        )
                        async def yes(self, i, b):
                            await i.response.defer(ephemeral=True)
                            self.value = True
                            self.stop()

                        @discord.ui.button(
                            label="いいえ", style=discord.ButtonStyle.danger
                        )
                        async def no(self, i, b):
                            await i.response.defer(ephemeral=True)
                            self.value = False
                            self.stop()

                    view = ConfirmView()
                    await interaction.followup.send(
                        embed=embed, view=view, ephemeral=True
                    )
                    timeout = await view.wait()
                    if view.value is True:
                        # 既存DMチャンネル探索
                        cat = await get_or_create_dm_category(ctx.guild)
                        for ch in cat.text_channels:
                            if (
                                ch.topic
                                and str(target.id) in ch.topic
                                and str(ctx.author.id) in ch.topic
                            ):
                                await interaction.followup.send(
                                    f"既にDMチャンネルが存在します: {ch.mention}",
                                    ephemeral=True,
                                )
                                return
                        # 新規DMチャンネル作成
                        overwrites = {
                            ctx.guild.default_role: discord.PermissionOverwrite(
                                read_messages=False
                            ),
                            ctx.author: discord.PermissionOverwrite(
                                read_messages=True, send_messages=True
                            ),
                            target: discord.PermissionOverwrite(
                                read_messages=True, send_messages=True
                            ),
                        }
                        ch = await ctx.guild.create_text_channel(
                            name=f"dm-{ctx.author.display_name}-{target.display_name}",
                            category=cat,
                            overwrites=overwrites,
                            topic=f"臨時DM: {ctx.author.id} <-> {target.id} | created: {datetime.utcnow().isoformat()}",
                        )
                        await set_external_app_commands_permission(ch, ctx.author)
                        await set_external_app_commands_permission(ch, target)
                        await interaction.followup.send(
                            f"✅ 臨時DMチャンネルを作成しました: {ch.mention}",
                            ephemeral=True,
                        )
                    elif view.value is False:
                        await interaction.followup.send(
                            "キャンセルしました", ephemeral=True
                        )
                    else:
                        await interaction.followup.send(
                            "タイムアウトしました", ephemeral=True
                        )

                await interaction.response.send_message(
                    embed=embed2, view=DmChoiceView(ctx), ephemeral=True
                )

            view = ModalInputView(
                label="DM UIを開く",
                on_button=on_dm_ui_button,
                button_emoji="💬",
                style=discord.ButtonStyle.primary,
                allowed_user_id=ctx.author.id,
                auto_delete_on_button=True,
            )
            await ctx.send(embed=embed, view=view)
            return
        if query.startswith("close"):
            # DMチャンネル削除
            if query.strip() == "close all":
                if not is_admin(str(ctx.author.id), ctx.guild.id, load_config()):
                    await ctx.send("❌ 管理者のみ全DM削除可能です")
                    return
                cat = await get_or_create_dm_category(ctx.guild)
                for ch in cat.text_channels:
                    await ch.delete()
                await ctx.send("✅ 臨時DMカテゴリ内の全DMを削除しました")
                return
            # 個別DM削除
            if ctx.channel.category and ctx.channel.category.name == DM_CATEGORY_NAME:
                await ctx.channel.delete()
            else:
                await ctx.send("❌ このコマンドは臨時DMチャンネル内でのみ有効です")
            return
        # 検索: ユーザー名/ID
        await ctx.send("❌ #dm <検索語> でのユーザー検索機能は廃止されました。ボタンUIから選択してください。")
        return
    register_command(bot, dm, aliases=None, admin=False)
    # tasks.loopで自動削除タスクを起動
    if not hasattr(bot, "_auto_delete_dm_started"):
        auto_delete_expired_dm_channels_task.start(bot)
        bot._auto_delete_dm_started = True


def create_dm_channel(ctx, author, target, interaction=None):
    """
    DMチャンネル作成処理（UIからも直接呼び出し可能）
    """
    from datetime import datetime

    async def inner():
        # DM作成数制限チェック
        user_dm_count = await count_user_dm_channels(ctx.guild, author)
        if user_dm_count >= 2:
            if interaction:
                await interaction.followup.send(
                    "❌ あなたが作成できる臨時DMチャンネルは2個までです", ephemeral=True
                )
            else:
                await ctx.send("❌ あなたが作成できる臨時DMチャンネルは2個までです")
            return
        cat = await get_or_create_dm_category(ctx.guild)
        # 既存DMチャンネル探索
        for ch in cat.text_channels:
            if ch.topic and str(target.id) in ch.topic and str(author.id) in ch.topic:
                if interaction:
                    await interaction.followup.send(
                        f"既にDMチャンネルが存在します: {ch.mention}", ephemeral=True
                    )
                else:
                    await ctx.send(f"既にDMチャンネルが存在します: {ch.mention}")
                return
        # 新規DMチャンネル作成
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            author: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            target: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        }
        ch = await ctx.guild.create_text_channel(
            name=f"dm-{author.display_name}-{target.display_name}",
            category=cat,
            overwrites=overwrites,
            topic=f"臨時DM: {author.id} <-> {target.id} | created: {datetime.utcnow().isoformat()}",
        )
        await set_external_app_commands_permission(ch, author)
        await set_external_app_commands_permission(ch, target)
        if interaction:
            await interaction.followup.send(
                f"✅ 臨時DMチャンネルを作成しました: {ch.mention}", ephemeral=True
            )
        else:
            await ctx.send(f"✅ 臨時DMチャンネルを作成しました: {ch.mention}")

    return asyncio.create_task(inner())
