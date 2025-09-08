from discord.ext import commands
from plugins import register_command
from plugins.common_ui import ModalInputView
import discord
import asyncio
from datetime import datetime
from lib.op import get_op_level, OP_GUILD_ADMIN, has_op
from plugins.Staff.util import StaffUtil
from typing import Optional
from discord.ui import View, Select

PRIVATE_CATEGORY_NAME = "PrivateRoom"
PRIVATE_TEXT_PREFIX = "private-"
PRIVATE_VC_PREFIX = "vc-"


def get_private_chats_from_channels(guild):
    """カテゴリからプライベートチャット情報を動的に取得"""
    category = discord.utils.get(guild.categories, name=PRIVATE_CATEGORY_NAME)
    if not category:
        return {}
    
    private_chats = {}
    for text_channel in category.text_channels:
        if text_channel.name.startswith(PRIVATE_TEXT_PREFIX):
            # 対応するVCを探す
            vc_name = text_channel.name.replace(PRIVATE_TEXT_PREFIX, PRIVATE_VC_PREFIX)
            vc_channel = discord.utils.get(category.voice_channels, name=vc_name)
            
            # メンバーリストを権限から取得
            members = []
            for target, overwrite in text_channel.overwrites.items():
                if isinstance(target, discord.Member) and overwrite.read_messages:
                    members.append(target.id)
            
            private_chats[str(text_channel.id)] = {
                "vc": vc_channel.id if vc_channel else None,
                "members": members,
                "name": text_channel.name.replace(PRIVATE_TEXT_PREFIX, "").replace("-", " ").title(),
                "created_at": text_channel.created_at.isoformat(),
                "created_by": None  # 権限から作成者を特定するのは困難なのでNone
            }
    
    return private_chats


def create_panel_embed(room_name, members, created_at=None, created_by=None, guild=None):
    if created_at:
        dt = datetime.fromisoformat(created_at)
    else:
        dt = datetime.utcnow()
    embed = discord.Embed(
        title=f"🔒 プライベートチャット: {room_name}",
        description="この部屋の操作パネルです。\n\n- 閉じる: チャンネルとVCを削除\n- メンバーリスト表示: 参加メンバー一覧を表示",
        color=0x5865f2,
        timestamp=dt,
    )
    embed.add_field(
        name="メンバー",
        value="\n".join([f"<@{m}>" for m in members]) or "(なし)",
        inline=False,
    )
    if created_at:
        unix_ts = int(dt.timestamp())
        embed.add_field(
            name="作成日時",
            value=f"<t:{unix_ts}:F>",  # タグのみ
            inline=False,
        )
    # 作成者名取得
    creator_name = None
    if created_by and guild:
        member = guild.get_member(created_by)
        if member:
            creator_name = member.display_name
    if creator_name:
        embed.set_footer(text=f"作成者: {creator_name} | 手動で削除してください")
    elif created_by:
        embed.set_footer(text=f"作成者: <@{created_by}> | 手動で削除してください")
    else:
        embed.set_footer(text="手動で削除してください")
    return embed


class PrivateChatPanel(discord.ui.View):
    def __init__(self, ctx, members, text_channel, vc_channel):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.members = members
        self.text_channel = text_channel
        self.vc_channel = vc_channel

    @discord.ui.button(label="閉じる", style=discord.ButtonStyle.danger, emoji="🚫")
    async def close_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        # interaction.guildがNoneの場合も考慮
        if not interaction.guild:
            await interaction.response.send_message("この操作はサーバー内でのみ可能です。", ephemeral=True)
            return
        member = interaction.guild.get_member(interaction.user.id)
        if not member or await get_op_level(member) < OP_GUILD_ADMIN:
            await interaction.response.send_message("ギルド管理者のみ操作可能です。", ephemeral=True)
            return
        await interaction.response.send_message("チャットを閉じます...", ephemeral=True)
        await self.text_channel.delete(reason="PrivateChat閉鎖")
        await self.vc_channel.delete(reason="PrivateChat閉鎖")

    @discord.ui.button(label="メンバーリスト表示", style=discord.ButtonStyle.primary, emoji="👥")
    async def show_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        # チャンネル情報から最新情報取得
        data = get_private_chats_from_channels(self.text_channel.guild)
        info = data.get(str(self.text_channel.id))
        if info:
            embed = create_panel_embed(self.text_channel.name, info.get("members", []), created_at=info.get("created_at"), created_by=info.get("created_by"), guild=self.text_channel.guild)
        else:
            embed = create_panel_embed(self.text_channel.name, self.members, guild=self.text_channel.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup_private_chat(ctx, room_name, members):
    created_at = datetime.utcnow().isoformat()  # 必ず現在時刻
    guild = ctx.guild
    guild_id = guild.id
    # --- 制限チェック ---
    data = get_private_chats_from_channels(guild)
    # カテゴリ内最大5個
    category = discord.utils.get(guild.categories, name=PRIVATE_CATEGORY_NAME)
    if category and len(category.text_channels) >= 5:
        await ctx.send("❌ このカテゴリに作成できるプライベートチャットは最大5個までです。")
        return
    # スタッフ1人1部屋まで（作成者チェックは権限ベースでは困難なのでスキップ）
    # カテゴリ取得/作成
    category = discord.utils.get(guild.categories, name=PRIVATE_CATEGORY_NAME)
    if not category:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
        }
        category = await guild.create_category(PRIVATE_CATEGORY_NAME, overwrites=overwrites)
    # チャンネル名生成
    base_name = room_name.lower().replace(" ", "-")
    text_name = PRIVATE_TEXT_PREFIX + base_name
    vc_name = PRIVATE_VC_PREFIX + base_name
    # 作成者＋メンバーのみ閲覧可
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
        ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True),
    }
    for m in members:
        member_obj = guild.get_member(m)
        if member_obj and member_obj != ctx.author:
            overwrites[member_obj] = discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True)
    # テキストチャンネル
    text_channel = await guild.create_text_channel(text_name, category=category, overwrites=overwrites)
    # VC
    vc_channel = await guild.create_voice_channel(vc_name, category=category, overwrites=overwrites)
    # 操作パネルEmbed
    embed = create_panel_embed(room_name, [ctx.author.id] + list(members), created_at=created_at, created_by=ctx.author.id, guild=guild)
    view = PrivateChatPanel(ctx, [ctx.author.id] + list(members), text_channel, vc_channel)
    panel_msg = await text_channel.send(embed=embed, view=view)
    await panel_msg.pin()
    # データベース保存は不要
    await ctx.send(f"✅ プライベートチャット '{room_name}' を作成しました。\n{text_channel.mention} / {vc_channel.mention}")


@commands.group(name="privateChat", invoke_without_command=True)
async def private_chat_cmd(ctx, *, room_name=None):
    if not await StaffUtil(ctx).is_staff():
        await ctx.send("このコマンドはスタッフ専用です。")
        return
    if not room_name:
        await ctx.send("使い方: #staff privateChat <部屋名>")
        return
    await setup_private_chat(ctx, room_name, [])


@private_chat_cmd.command(name="modify")
async def private_chat_modify(ctx):
    guild = ctx.guild
    if not await StaffUtil(ctx).is_staff():
        await ctx.send("このコマンドはスタッフ専用です。")
        return
    
    # PrivateRoomカテゴリ内でのみ実行可能
    if not ctx.channel.category or ctx.channel.category.name != PRIVATE_CATEGORY_NAME:
        await ctx.send("このコマンドはPrivateRoomカテゴリ内のテキストチャンネルで実行してください。")
        return
    
    # プライベートチャットかどうか確認
    data = get_private_chats_from_channels(guild)
    chat = data.get(str(ctx.channel.id))
    if not chat:
        await ctx.send("このチャンネルは管理対象のプライベートチャットではありません。")
        return
    
    # 権限チェック：作成者または管理者のみ（チャンネル権限で判定）
    user_perms = ctx.channel.permissions_for(ctx.author)
    is_admin = has_op(ctx.author, OP_GUILD_ADMIN)
    
    # チャンネルの管理権限があるか、または管理者権限があるかをチェック
    if not (user_perms.manage_channels or is_admin):
        await ctx.send("❌ この操作はチャンネルの管理権限を持つメンバーまたはギルド管理者のみ可能です。")
        return
    
    # 現在のメンバー情報を取得
    current_members = chat.get("members", [])
    
    # 操作選択用のEmbed
    embed = discord.Embed(
        title="🔧 プライベートチャット管理",
        description=f"**チャンネル**: {ctx.channel.mention}\n**現在のメンバー数**: {len(current_members)}人",
        color=0x5865f2
    )
    
    if current_members:
        member_list = []
        for member_id in current_members[:10]:  # 最大10人まで表示
            member = guild.get_member(member_id)
            if member:
                member_list.append(f"• {member.display_name}")
            else:
                member_list.append(f"• <@{member_id}>")
        
        if len(current_members) > 10:
            member_list.append(f"... 他{len(current_members) - 10}人")
        
        embed.add_field(
            name="現在のメンバー",
            value="\n".join(member_list),
            inline=False
        )
    
    # 操作ボタンを作成
    view = PrivateChatModifyView(ctx, chat)
    await ctx.send(embed=embed, view=view)


class PrivateChatModifyView(discord.ui.View):
    def __init__(self, ctx, chat_info):
        super().__init__(timeout=300)  # 5分でタイムアウト
        self.ctx = ctx
        self.chat_info = chat_info
    
    @discord.ui.button(label="メンバー追加", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ コマンド実行者のみが操作できます。", ephemeral=True)
            return
        
        # モーダルでメンバー名検索
        modal = MemberSearchModal(self.ctx, self.chat_info)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="メンバー削除", style=discord.ButtonStyle.secondary, emoji="➖")
    async def remove_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ コマンド実行者のみが操作できます。", ephemeral=True)
            return
        
        # 現在のメンバーから削除対象を選択
        current_members = []
        for member_id in self.chat_info.get("members", []):
            member = self.ctx.guild.get_member(member_id)
            if member and member != self.ctx.author:  # 作成者以外
                current_members.append(member)
        
        if not current_members:
            await interaction.response.send_message("❌ 削除可能なメンバーがいません。", ephemeral=True)
            return
        
        # 削除選択用のView
        view = MemberRemoveView(self.ctx, self.chat_info, current_members)
        embed = discord.Embed(
            title="➖ メンバー削除",
            description="削除するメンバーを選択してください。",
            color=0xff6b6b
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="メンバーリスト", style=discord.ButtonStyle.success, emoji="📋")
    async def show_member_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 最新のメンバー情報を取得
        data = get_private_chats_from_channels(self.ctx.guild)
        updated_chat = data.get(str(self.ctx.channel.id))
        if not updated_chat:
            updated_chat = self.chat_info
        
        embed = create_panel_embed(
            self.ctx.channel.name.replace(PRIVATE_TEXT_PREFIX, "").replace("-", " ").title(),
            updated_chat.get("members", []),
            created_at=updated_chat.get("created_at"),
            created_by=updated_chat.get("created_by"),
            guild=self.ctx.guild
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MemberSearchModal(discord.ui.Modal):
    def __init__(self, ctx, chat_info):
        super().__init__(title="メンバー検索・追加")
        self.ctx = ctx
        self.chat_info = chat_info
    
    search_input = discord.ui.TextInput(
        label="追加するメンバー名",
        placeholder="例: こう君",
        max_length=50
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        keyword = self.search_input.value.strip().lower()
        guild = self.ctx.guild
        
        # 現在のメンバーを取得
        existing = set(self.chat_info.get("members", []))
        
        # メンバー検索
        candidates = [
            m for m in guild.members 
            if m.id not in existing and not m.bot and 
            (keyword in m.display_name.lower() or keyword in m.name.lower())
        ]
        
        if not candidates:
            await interaction.response.send_message("❌ 該当するメンバーが見つかりません。", ephemeral=True)
            return
        
        # 1人なら即追加
        if len(candidates) == 1:
            await self._add_member(interaction, candidates[0])
            return
        
        # 複数人の場合は選択UI
        view = MemberSelectView(self.ctx, self.chat_info, candidates[:25])
        embed = discord.Embed(
            title="➕ メンバー選択",
            description=f"「{keyword}」の検索結果から追加するメンバーを選択してください。",
            color=0x4fc3f7
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def _add_member(self, interaction, member):
        # 権限を更新
        overwrites = self.ctx.channel.overwrites
        overwrites[member] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True, connect=True, speak=True
        )
        await self.ctx.channel.edit(overwrites=overwrites)
        
        # VCの権限も更新
        vc = self.ctx.guild.get_channel(self.chat_info.get("vc"))
        if vc:
            await vc.edit(overwrites=overwrites)
        
        await interaction.response.send_message(
            f"✅ {member.display_name} をプライベートチャットに追加しました。", 
            ephemeral=True
        )


class MemberSelectView(discord.ui.View):
    def __init__(self, ctx, chat_info, candidates):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.chat_info = chat_info
        self.candidates = candidates
        
        # 最大25人まで選択肢に追加
        options = [
            discord.SelectOption(
                label=member.display_name,
                value=str(member.id),
                description=f"@{member.name}"
            )
            for member in candidates
        ]
        
        self.member_select = discord.ui.Select(
            placeholder="追加するメンバーを選択...",
            min_values=1,
            max_values=min(5, len(options)),
            options=options
        )
        self.member_select.callback = self.select_callback
        self.add_item(self.member_select)
    
    async def select_callback(self, interaction: discord.Interaction):
        selected_ids = [int(value) for value in self.member_select.values]
        
        # 権限を更新
        overwrites = self.ctx.channel.overwrites
        added_members = []
        
        for member_id in selected_ids:
            member = self.ctx.guild.get_member(member_id)
            if member:
                overwrites[member] = discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, connect=True, speak=True
                )
                added_members.append(member.display_name)
        
        await self.ctx.channel.edit(overwrites=overwrites)
        
        # VCの権限も更新
        vc = self.ctx.guild.get_channel(self.chat_info.get("vc"))
        if vc:
            await vc.edit(overwrites=overwrites)
        
        await interaction.response.send_message(
            f"✅ 以下のメンバーをプライベートチャットに追加しました:\n• {chr(10).join(added_members)}",
            ephemeral=True
        )
        self.stop()


class MemberRemoveView(discord.ui.View):
    def __init__(self, ctx, chat_info, members):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.chat_info = chat_info
        self.members = members
        
        # 削除対象メンバーの選択肢
        options = [
            discord.SelectOption(
                label=member.display_name,
                value=str(member.id),
                description=f"@{member.name}"
            )
            for member in members[:25]  # 最大25人
        ]
        
        self.member_select = discord.ui.Select(
            placeholder="削除するメンバーを選択...",
            min_values=1,
            max_values=min(5, len(options)),
            options=options
        )
        self.member_select.callback = self.select_callback
        self.add_item(self.member_select)
    
    async def select_callback(self, interaction: discord.Interaction):
        selected_ids = [int(value) for value in self.member_select.values]
        
        # 権限を削除
        overwrites = self.ctx.channel.overwrites
        removed_members = []
        
        for member_id in selected_ids:
            member = self.ctx.guild.get_member(member_id)
            if member and member in overwrites:
                del overwrites[member]
                removed_members.append(member.display_name)
        
        await self.ctx.channel.edit(overwrites=overwrites)
        
        # VCの権限も削除
        vc = self.ctx.guild.get_channel(self.chat_info.get("vc"))
        if vc:
            vc_overwrites = vc.overwrites
            for member_id in selected_ids:
                member = self.ctx.guild.get_member(member_id)
                if member and member in vc_overwrites:
                    del vc_overwrites[member]
            await vc.edit(overwrites=vc_overwrites)
        
        await interaction.response.send_message(
            f"✅ 以下のメンバーをプライベートチャットから削除しました:\n• {chr(10).join(removed_members)}",
            ephemeral=True
        )
        self.stop()





@private_chat_cmd.command(name="close")
async def private_chat_close(ctx, *, arg: Optional[str] = None):
    guild_id = ctx.guild.id
    guild = ctx.guild
    data = get_private_chats_from_channels(guild)
    # 引数なし: 現在のチャンネルを閉鎖（作成者または管理者のみ）
    if not arg:
        chat = data.get(str(ctx.channel.id))
        if not chat:
            await ctx.send("このチャンネルは管理対象のプライベートチャットではありません。")
            return
        # 作成者チェックは困難なので管理者のみに変更
        is_admin = has_op(ctx.author, OP_GUILD_ADMIN)
        if not is_admin:
            await ctx.send("この操作はギルド管理者のみ可能です。")
            return
        text_ch = ctx.channel
        vc_ch = ctx.guild.get_channel(chat.get("vc"))
        try:
            if text_ch:
                await text_ch.delete(reason="PrivateChat手動閉鎖")
            if vc_ch:
                await vc_ch.delete(reason="PrivateChat手動閉鎖")
        except discord.errors.NotFound:
            pass
        except Exception as e:
            await ctx.send(f"削除中にエラーが発生しました: {e}")
            return
        # データベース保存は不要
        return
    # all: 全て閉鎖（管理者のみ）
    if arg.strip() == "all":
        if not has_op(ctx.author, OP_GUILD_ADMIN):
            await ctx.send("このコマンドはギルド管理者専用です。")
            return
        for text_id, info in list(data.items()):
            text_ch = ctx.guild.get_channel(int(text_id))
            vc_ch = ctx.guild.get_channel(info.get("vc"))
            try:
                if text_ch:
                    await text_ch.delete(reason="PrivateChat一括閉鎖")
                if vc_ch:
                    await vc_ch.delete(reason="PrivateChat一括閉鎖")
            except discord.errors.NotFound:
                pass
            except Exception as e:
                await ctx.send(f"削除中にエラーが発生しました: {e}")
        # データベース保存は不要
        return
    # チャンネルID指定: 管理者のみ
    if arg.isdigit():
        text_id = arg
        chat = data.get(text_id)
        if not chat:
            await ctx.send("指定されたチャンネルIDのプライベートチャットが見つかりません。"); return
        is_admin = has_op(ctx.author, OP_GUILD_ADMIN)
        if not is_admin:
            await ctx.send("この操作はギルド管理者のみ可能です。")
            return
        text_ch = ctx.guild.get_channel(int(text_id))
        vc_ch = ctx.guild.get_channel(chat.get("vc"))
        try:
            if text_ch:
                await text_ch.delete(reason="PrivateChat手動閉鎖")
            if vc_ch:
                await vc_ch.delete(reason="PrivateChat手動閉鎖")
        except discord.errors.NotFound:
            pass
        except Exception as e:
            await ctx.send(f"削除中にエラーが発生しました: {e}")
            return
        # データベース保存は不要
        return
    # 部屋名指定: 管理者のみ
    found = False
    for text_id, chat in list(data.items()):
        if chat.get("name") == arg:
            is_admin = has_op(ctx.author, OP_GUILD_ADMIN)
            if not is_admin:
                await ctx.send("この操作はギルド管理者のみ可能です。")
                return
            text_ch = ctx.guild.get_channel(int(text_id))
            vc_ch = ctx.guild.get_channel(chat.get("vc"))
            try:
                if text_ch:
                    await text_ch.delete(reason="PrivateChat手動閉鎖")
                if vc_ch:
                    await vc_ch.delete(reason="PrivateChat手動閉鎖")
            except discord.errors.NotFound:
                pass
            except Exception as e:
                await ctx.send(f"削除中にエラーが発生しました: {e}")
                return
            # データベース保存は不要
            found = True
            break
    # データベース保存は不要
    if not found:
        await ctx.send("❌ 指定名のプライベートチャットが見つかりません。")


@private_chat_cmd.command(name="list")
async def private_chat_list(ctx):
    guild_id = ctx.guild.id
    guild = ctx.guild
    data = get_private_chats_from_channels(guild)
    if not data:
        await ctx.send("プライベートチャットは存在しません。")
        return
    desc = ""
    for text_id, info in data.items():
        name = info.get("name", "(不明)")
        created_by = info.get("created_by")
        created_at = info.get("created_at")
        members = info.get("members", [])
        unix_ts = None
        if created_at:
            try:
                dt = datetime.fromisoformat(created_at)
                unix_ts = int(dt.timestamp())
            except Exception:
                unix_ts = None
        ts_str = f"<t:{unix_ts}:F>" if unix_ts else "-"
        creator_str = f"<@{created_by}>" if created_by else "(不明)"
        desc += f"**{name}**\n- 作成者: {creator_str}\n- 作成日時: {ts_str}\n- メンバー: {', '.join([f'<@{m}>' for m in members])}\n\n"
    embed = discord.Embed(title="プライベートチャット一覧", description=desc, color=0x5865f2)
    await ctx.send(embed=embed)


def setup(bot=None):
    # bot引数は互換用。未使用。
    return private_chat_cmd
