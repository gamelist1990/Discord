from discord.ext import commands
from plugins import register_command
from plugins.common_ui import ModalInputView
import discord
import asyncio
from datetime import datetime
from lib.op import get_op_level, OP_GUILD_ADMIN, has_op
from plugins.Staff.util import StaffUtil
from DataBase import get_guild_data, set_guild_data
from typing import Optional
from discord.ui import View, Select

PRIVATE_CATEGORY_NAME = "PrivateRoom"
PRIVATE_TEXT_PREFIX = "private-"
PRIVATE_VC_PREFIX = "vc-"


def save_private_chats_to_db(guild_id, data):
    guild_data = get_guild_data(guild_id)
    guild_data["private_chats"] = data
    set_guild_data(guild_id, guild_data)


def get_private_chats(guild_id):
    guild_data = get_guild_data(guild_id)
    return guild_data.get("private_chats", {})


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
        # DBから削除
        data = get_private_chats(self.text_channel.guild.id)
        for k, v in list(data.items()):
            if int(k) == self.text_channel.id:
                data.pop(k)
        save_private_chats_to_db(self.text_channel.guild.id, data)

    @discord.ui.button(label="メンバーリスト表示", style=discord.ButtonStyle.primary, emoji="👥")
    async def show_members(self, interaction: discord.Interaction, button: discord.ui.Button):
        # DBから最新情報取得
        data = get_private_chats(self.text_channel.guild.id)
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
    data = get_private_chats(guild_id)
    # カテゴリ内最大5個
    category = discord.utils.get(guild.categories, name=PRIVATE_CATEGORY_NAME)
    if category and len(category.text_channels) >= 5:
        await ctx.send("❌ このカテゴリに作成できるプライベートチャットは最大5個までです。")
        return
    # スタッフ1人1部屋まで
    for info in data.values():
        if info.get("created_by") == ctx.author.id:
            await ctx.send("❌ あなたは既にプライベートチャットを作成しています。1人1部屋までです。")
            return
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
    # DBに保存
    data = get_private_chats(guild_id)
    data[str(text_channel.id)] = {
        "vc": vc_channel.id,
        "members": [ctx.author.id] + list(members),
        "created_by": ctx.author.id,
        "created_at": created_at,
        "name": room_name,
    }
    save_private_chats_to_db(guild_id, data)
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


@private_chat_cmd.command(name="add")
async def private_chat_add(ctx, *, users):
    guild_id = ctx.guild.id
    if not await StaffUtil(ctx).is_staff():
        await ctx.send("このコマンドはスタッフ専用です。")
        return
    # 対象テキストチャンネルを取得
    if not ctx.channel.category or ctx.channel.category.name != PRIVATE_CATEGORY_NAME:
        await ctx.send("このコマンドはPrivateRoomカテゴリ内のテキストチャンネルで実行してください。")
        return
    data = get_private_chats(guild_id)
    chat = data.get(str(ctx.channel.id))
    if not chat:
        await ctx.send("このチャンネルは管理対象のプライベートチャットではありません。")
        return
    # ユーザーID/メンションをパース
    user_ids = set()
    for part in users.replace("<@!", "<@").replace("<@", "").replace(">", "").split(","):
        part = part.strip()
        if part.isdigit():
            user_ids.add(int(part))
    if not user_ids:
        await ctx.send("追加するユーザーを@メンションまたはIDで指定してください。複数はカンマ区切り。")
        return
    # 既存メンバーに追加
    chat["members"] = list(set(chat["members"]) | user_ids)
    # 権限を更新
    overwrites = ctx.channel.overwrites
    for uid in user_ids:
        member = ctx.guild.get_member(uid)
        if member:
            overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True)
    await ctx.channel.edit(overwrites=overwrites)
    vc = ctx.guild.get_channel(chat["vc"])
    if vc:
        await vc.edit(overwrites=overwrites)
    save_private_chats_to_db(guild_id, data)
    await ctx.send(f"✅ メンバーを追加しました: {', '.join([f'<@{u}>' for u in user_ids])}")


@private_chat_cmd.command(name="add_ui")
async def private_chat_add_ui(ctx):
    guild = ctx.guild
    guild_id = guild.id
    if not await StaffUtil(ctx).is_staff():
        await ctx.send("このコマンドはスタッフ専用です。")
        return
    if not ctx.channel.category or ctx.channel.category.name != PRIVATE_CATEGORY_NAME:
        await ctx.send("このコマンドはPrivateRoomカテゴリ内のテキストチャンネルで実行してください。")
        return
    data = get_private_chats(guild_id)
    chat = data.get(str(ctx.channel.id))
    if not chat:
        await ctx.send("このチャンネルは管理対象のプライベートチャットではありません。")
        return
    existing = set(chat["members"])
    # ModalInputViewでモーダルUIを出す
    async def on_submit(interaction, value, recipient, view):
        keyword = value.strip().lower()
        candidates = [m for m in guild.members if m.id not in existing and not m.bot and (keyword in m.display_name.lower() or keyword in m.name.lower())]
        if not candidates:
            await interaction.response.send_message("該当するメンバーが見つかりません。", ephemeral=True)
            return
        # 1～4件の場合はSelectを使わずボタンで選択、1件なら即追加
        if len(candidates) == 1:
            uid = candidates[0].id
            chat["members"] = list(set(chat["members"]) | {uid})
            overwrites = ctx.channel.overwrites
            member = guild.get_member(uid)
            if member:
                overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True)
            await ctx.channel.edit(overwrites=overwrites)
            vc = guild.get_channel(chat["vc"])
            if vc:
                await vc.edit(overwrites=overwrites)
            save_private_chats_to_db(guild_id, data)
            await interaction.response.send_message(f"✅ メンバーを追加しました: {candidates[0].display_name}", ephemeral=True)
            return
        elif len(candidates) < 5:
            # ボタンで選択肢を出す
            class ButtonView(View):
                def __init__(self):
                    super().__init__(timeout=60)
                    for m in candidates:
                        self.add_item(self.MemberButton(m))
                class MemberButton(discord.ui.Button):
                    def __init__(self, member):
                        super().__init__(label=member.display_name, style=discord.ButtonStyle.primary)
                        self.member = member
                    async def callback(self, interaction: discord.Interaction):
                        uid = self.member.id
                        chat["members"] = list(set(chat["members"]) | {uid})
                        overwrites = ctx.channel.overwrites
                        member = guild.get_member(uid)
                        if member:
                            overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True)
                        await ctx.channel.edit(overwrites=overwrites)
                        vc = guild.get_channel(chat["vc"])
                        if vc:
                            await vc.edit(overwrites=overwrites)
                        save_private_chats_to_db(guild_id, data)
                        await interaction.response.send_message(f"✅ メンバーを追加しました: {self.member.display_name}", ephemeral=True)
                        if self.view:
                            self.view.stop()
            await interaction.response.send_message("追加するメンバーを選択してください：", view=ButtonView(), ephemeral=True)
            return
        # 5件以上の場合のみSelectを表示
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id), description=m.name)
            for m in candidates[:25]
        ]
        class MemberSelectView(View):
            def __init__(self):
                super().__init__(timeout=60)
                self.add_item(self.MemberSelect())
            class MemberSelect(Select):
                def __init__(self):
                    super().__init__(placeholder="追加するメンバーを選択", min_values=1, max_values=5, options=options)
                async def callback(self, interaction: discord.Interaction):
                    user_ids = set(int(v) for v in self.values)
                    chat["members"] = list(set(chat["members"]) | user_ids)
                    overwrites = ctx.channel.overwrites
                    for uid in user_ids:
                        member = guild.get_member(uid)
                        if member:
                            overwrites[member] = discord.PermissionOverwrite(read_messages=True, send_messages=True, connect=True, speak=True)
                    await ctx.channel.edit(overwrites=overwrites)
                    vc = guild.get_channel(chat["vc"])
                    if vc:
                        await vc.edit(overwrites=overwrites)
                    save_private_chats_to_db(guild_id, data)
                    names = [guild.get_member(uid).display_name for uid in user_ids if guild.get_member(uid)]
                    await interaction.response.send_message(f"✅ メンバーを追加しました: {', '.join(names)}", ephemeral=True)
                    if self.view:
                        self.view.stop()
        await interaction.response.send_message("追加するメンバーを選択してください：", view=MemberSelectView(), ephemeral=True)
    view = ModalInputView(
        label="メンバー名で追加",
        on_submit=on_submit,
        modal_title="メンバー名で検索",
        placeholder="例: こう君",
        text_label="追加したいメンバー名（部分一致可）",
        style=discord.ButtonStyle.primary,
        max_length=32,
        allowed_user_id=ctx.author.id
    )
    await ctx.send("追加したいメンバー名を入力してください：", view=view)


@private_chat_cmd.command(name="close")
async def private_chat_close(ctx, *, arg: Optional[str] = None):
    guild_id = ctx.guild.id
    data = get_private_chats(guild_id)
    # 引数なし: 現在のチャンネルを閉鎖（作成者または管理者のみ）
    if not arg:
        chat = data.get(str(ctx.channel.id))
        if not chat:
            await ctx.send("このチャンネルは管理対象のプライベートチャットではありません。")
            return
        is_creator = chat.get("created_by") == ctx.author.id
        is_admin = has_op(ctx.author, OP_GUILD_ADMIN)
        if not (is_creator or is_admin):
            await ctx.send("この操作は作成者またはギルド管理者のみ可能です。")
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
        data.pop(str(ctx.channel.id), None)
        save_private_chats_to_db(guild_id, data)
        return
    # all: 全て閉鎖（管理者のみ）
    if arg.strip() == "all":
        if not has_op(ctx.author, OP_GUILD_ADMIN):
            await ctx.send("このコマンドはギルド管理者専用です。")
            return
        to_delete = []
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
            to_delete.append(str(text_id))
        for tid in to_delete:
            data.pop(tid, None)
        save_private_chats_to_db(guild_id, data)
        return
    # チャンネルID指定: 作成者または管理者のみ
    if arg.isdigit():
        text_id = arg
        chat = data.get(text_id)
        if not chat:
            await ctx.send("指定されたチャンネルIDのプライベートチャットが見つかりません。"); return
        is_creator = chat.get("created_by") == ctx.author.id
        is_admin = has_op(ctx.author, OP_GUILD_ADMIN)
        if not (is_creator or is_admin):
            await ctx.send("この操作は作成者またはギルド管理者のみ可能です。")
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
        data.pop(str(text_id), None)
        save_private_chats_to_db(guild_id, data)
        return
    # 部屋名指定: 作成者または管理者のみ
    found = False
    for text_id, chat in list(data.items()):
        if chat.get("name") == arg:
            is_creator = chat.get("created_by") == ctx.author.id
            is_admin = has_op(ctx.author, OP_GUILD_ADMIN)
            if not (is_creator or is_admin):
                await ctx.send("この操作は作成者またはギルド管理者のみ可能です。")
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
            data.pop(str(text_id), None)
            found = True
            break
    save_private_chats_to_db(guild_id, data)
    if not found:
        await ctx.send("❌ 指定名のプライベートチャットが見つかりません。")


@private_chat_cmd.command(name="list")
async def private_chat_list(ctx):
    guild_id = ctx.guild.id
    data = get_private_chats(guild_id)
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
        desc += f"**{name}**\n- 作成者: <@{created_by}>\n- 作成日時: {ts_str}\n- メンバー: {', '.join([f'<@{m}>' for m in members])}\n\n"
    embed = discord.Embed(title="プライベートチャット一覧", description=desc, color=0x5865f2)
    await ctx.send(embed=embed)


def setup(bot):
    return private_chat_cmd
