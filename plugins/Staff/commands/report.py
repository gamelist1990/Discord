from discord.ext import commands
import discord
from DataBase import get_guild_data, update_guild_data
import datetime
import io
from plugins.Staff.util import StaffUtil

@commands.command(name="report")
async def report_cmd(ctx):
    util = StaffUtil(ctx)
    if not (await util.is_staff()):
        await ctx.send("このコマンドはスタッフ専用です。")
        return
    guild_id = ctx.guild.id
    data = get_guild_data(guild_id)
    hansei = data.get("hansei_reports", {})
    now = datetime.datetime.now(datetime.timezone.utc)
    changed = False
    expired = []
    for uid, v in list(hansei.items()):
        try:
            expire = datetime.datetime.fromisoformat(v["expire"])
            if now > expire:
                expired.append(uid)
        except Exception:
            expired.append(uid)
    for uid in expired:
        del hansei[uid]
        changed = True
    if changed:
        update_guild_data(guild_id, "hansei_reports", hansei)
    if not hansei:
        await ctx.send("現在、提出された反省文はありません。"); return

    # ページング用: 反省文リスト
    hansei_items = list(hansei.items())
    page_size = 1
    total_pages = (len(hansei_items) + page_size - 1) // page_size

    class HanseiView(discord.ui.View):
        def __init__(self, author_id, page=0):
            super().__init__(timeout=180)
            self.author_id = author_id
            self.page = page
            self.update_items()

        def update_items(self):
            self.clear_items()
            start = self.page * page_size
            end = start + page_size
            page_items = hansei_items[start:end]
            options = [
                discord.SelectOption(label=f"{v.get('user_name','?')} ({uid})", value=uid)
                for uid, v in page_items
            ]
            select = HanseiSelect(options, self.author_id)
            select.view_ref = self
            self.add_item(select)
            if self.page > 0:
                self.add_item(PrevButton(self))
            if self.page < total_pages - 1:
                self.add_item(NextButton(self))

    from typing import Optional
    
    class HanseiSelect(discord.ui.Select):
        view_ref: Optional["HanseiView"]  # 型アノテーションを追加
    
        def __init__(self, options, author_id):
            super().__init__(placeholder="反省文提出者を選択", min_values=1, max_values=1, options=options)
            self.author_id = author_id
            self.view_ref = None  # 明示的に属性を定義
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            uid = self.values[0]
            # 選択時はApproveViewでボタンを表示
            await interaction.response.edit_message(
                content=f"「このユーザーを調べる」ボタンを押すと反省文が公開されます。",
                view=ApproveView(uid, self.author_id, self.view)
            )

    class ApproveView(discord.ui.View):
        def __init__(self, uid, author_id, parent_view):
            super().__init__(timeout=120)
            self.uid = uid
            self.author_id = author_id
            self.parent_view = parent_view
            self.add_item(InspectButton(self.uid, self.author_id, self))

    class InspectButton(discord.ui.Button):
        def __init__(self, uid, author_id, approve_view):
            super().__init__(label="このユーザーを調べる", style=discord.ButtonStyle.primary)
            self.uid = uid
            self.author_id = author_id
            self.approve_view = approve_view
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            v = hansei[self.uid]
            user_name = v.get("user_name", "?")
            text = v["text"]
            expire_str = v.get("expire", "?")
            
            # 期限をパース
            try:
                expire_dt = datetime.datetime.fromisoformat(expire_str)
                expire_timestamp = f"<t:{int(expire_dt.timestamp())}:F>"
                expire_relative = f"<t:{int(expire_dt.timestamp())}:R>"
            except:
                expire_timestamp = expire_str
                expire_relative = "不明"
            
            # ユーザー情報を取得
            member = ctx.guild.get_member(int(self.uid))
            avatar_url = member.display_avatar.url if member else "https://cdn.discordapp.com/embed/avatars/0.png"
              # 反省文の長さに応じて表示方法を調整（コードブロック記法6文字+安全マージンを考慮）
            if len(text) <= 350:
                # 短い場合はEmbedのfieldに表示
                embed = discord.Embed(
                    title="📝 反省文詳細",
                    description=f"**{user_name}** さんの反省文",
                    color=0x3498DB,
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="👤 ユーザー", value=f"{user_name} (ID: {self.uid})", inline=True)
                embed.add_field(name="⏰ 期限", value=expire_timestamp, inline=True)
                embed.add_field(name="📅 期限まで", value=expire_relative, inline=True)
                embed.add_field(name="📄 反省文内容", value=f"```\n{text}\n```", inline=False)
                embed.set_footer(text="反省文確認システム", icon_url=ctx.bot.user.display_avatar.url)
                
                await interaction.response.edit_message(
                    content=None,
                    embed=embed,
                    view=DetailView(self.uid, self.author_id, self.approve_view.parent_view)
                )
            else:
                # 長い場合はEmbedとファイル添付の併用
                file = discord.File(io.BytesIO(text.encode("utf-8")), filename=f"{user_name}_反省文.txt")
                embed = discord.Embed(
                    title="📝 反省文詳細",
                    description=f"**{user_name}** さんの反省文\n\n📎 **内容が長いためファイルで表示しています**",
                    color=0x3498DB,
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.set_thumbnail(url=avatar_url)
                embed.add_field(name="👤 ユーザー", value=f"{user_name} (ID: {self.uid})", inline=True)
                embed.add_field(name="⏰ 期限", value=expire_timestamp, inline=True)
                embed.add_field(name="📅 期限まで", value=expire_relative, inline=True)
                embed.add_field(name="📊 文字数", value=f"{len(text)}文字", inline=True)
                embed.set_footer(text="反省文確認システム", icon_url=ctx.bot.user.display_avatar.url)
                
                await interaction.response.edit_message(
                    content=None,
                    embed=embed,
                    attachments=[file],
                    view=DetailView(self.uid, self.author_id, self.approve_view.parent_view)
                )

    class DetailView(discord.ui.View):
        def __init__(self, uid, author_id, parent_view):
            super().__init__(timeout=180)
            self.uid = uid
            self.author_id = author_id
            self.parent_view = parent_view
            self.add_item(BackButton(self.parent_view))
            self.add_item(ApproveDetailButton(self.uid, self.author_id))
            self.add_item(RejectDetailButton(self.uid, self.author_id))

    class ApproveDetailButton(discord.ui.Button):
        def __init__(self, uid, author_id):
            super().__init__(label="✅ 許諾(解除)", style=discord.ButtonStyle.success)
            self.uid = uid
            self.author_id = author_id
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            member = ctx.guild.get_member(int(self.uid))
            v = hansei[self.uid]
            user_name = v.get("user_name", "?")
            if member:
                try:
                    await member.edit(timed_out_until=None, reason="スタッフによる解除")
                except Exception:
                    pass
            hansei.pop(self.uid, None)
            update_guild_data(guild_id, "hansei_reports", hansei)
            
            success_embed = discord.Embed(
                title="✅ タイムアウト解除完了",
                description=f"**{user_name}** のタイムアウトを解除し、反省文を削除しました。",
                color=0x2ECC71,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            success_embed.set_footer(text="処理完了")
            await interaction.response.edit_message(embed=success_embed, view=None)

    class RejectDetailButton(discord.ui.Button):
        def __init__(self, uid, author_id):
            super().__init__(label="❌ 拒否(削除)", style=discord.ButtonStyle.danger)
            self.uid = uid
            self.author_id = author_id
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            v = hansei[self.uid]
            user_name = v.get("user_name", "?")
            hansei.pop(self.uid, None)
            update_guild_data(guild_id, "hansei_reports", hansei)
            
            reject_embed = discord.Embed(
                title="❌ 反省文削除完了",
                description=f"**{user_name}** の反省文を削除しました。",
                color=0xE74C3C,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            reject_embed.set_footer(text="処理完了")
            await interaction.response.edit_message(embed=reject_embed, view=None)

    class BackButton(discord.ui.Button):
        def __init__(self, parent_view):
            super().__init__(label="⬅️ 戻る", style=discord.ButtonStyle.secondary)
            self.parent_view = parent_view
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.parent_view.author_id:
                await interaction.response.send_message("この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            
            list_embed = discord.Embed(
                title="📋 反省文一覧",
                description="確認したいユーザーを選択してください。",
                color=0x3498DB,
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            list_embed.add_field(name="📊 総数", value=f"{len(hansei)}件", inline=True)
            list_embed.set_footer(text="反省文確認システム", icon_url=ctx.bot.user.display_avatar.url)
            
            await interaction.response.edit_message(
                content=None,
                embed=list_embed,
                view=self.parent_view
            )

    class PrevButton(discord.ui.Button):
        def __init__(self, view):
            super().__init__(label="前へ", style=discord.ButtonStyle.secondary)
            self.view_ref = view
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.view_ref.author_id:
                await interaction.response.send_message("この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            self.view_ref.page -= 1
            self.view_ref.update_items()
            await interaction.response.edit_message(view=self.view_ref)

    class NextButton(discord.ui.Button):
        def __init__(self, view):
            super().__init__(label="次へ", style=discord.ButtonStyle.secondary)
            self.view_ref = view
        async def callback(self, interaction: discord.Interaction):
            if interaction.user.id != self.view_ref.author_id:
                await interaction.response.send_message("この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            self.view_ref.page += 1
            self.view_ref.update_items()
            await interaction.response.edit_message(view=self.view_ref)

    await ctx.send(
        embed=discord.Embed(
            title="📋 反省文一覧",
            description="確認したいユーザーを選択してください。",
            color=0x3498DB,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        ).add_field(name="📊 総数", value=f"{len(hansei)}件", inline=True).set_footer(text="反省文確認システム", icon_url=ctx.bot.user.display_avatar.url),
        view=HanseiView(ctx.author.id)
    )
