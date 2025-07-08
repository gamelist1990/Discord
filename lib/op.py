"""
op.py - 権限管理サブモジュール
op = 0: 全員
op = 1: 何かしらのロールあり
op = 2: Staff
op = 3: ギルドアドミン
op = 4: グローバルアドミン
"""

import discord
import json
import os
from DataBase import get_guild_value
from index import load_config

# opレベル定義
OP_EVERYONE = 0
OP_HAS_ROLE = 1
OP_STAFF = 2
OP_GUILD_ADMIN = 3
OP_GLOBAL_ADMIN = 4

# --- 権限ID取得 ---
def get_global_admin_ids():
    config = load_config()
    return set(str(uid) for uid in config.get("globalAdmins", []))

def get_guild_admin_ids(guild_id):
    config = load_config()
    return set(str(uid) for uid in config.get("guildAdmins", {}).get(str(guild_id), []))

def get_staff_role_id(guild_id):
    return str(get_guild_value(guild_id, "staffRole"))


async def get_op_level(member: discord.Member) -> int:
    user_id = str(member.id)
    guild_id = str(member.guild.id)
    global_admins = get_global_admin_ids()
    guild_admins = get_guild_admin_ids(guild_id)
    staff_role_id = get_staff_role_id(guild_id)
    # グローバル管理者
    if user_id in global_admins:
        return OP_GLOBAL_ADMIN
    # ギルド管理者（guildAdminsが未設定や空でもOK）
    if guild_admins and user_id in guild_admins:
        return OP_GUILD_ADMIN
    # スタッフ（staffRoleが未設定や空ならスキップ）
    if staff_role_id and staff_role_id != 'None' and any(str(r.id) == staff_role_id for r in member.roles):
        return OP_STAFF
    # 何かしらのロール（@everyone以外）
    if len([r for r in member.roles if r.name != '@everyone']) > 0:
        return OP_HAS_ROLE
    return OP_EVERYONE


def has_op(member: discord.Member, required_op: int) -> bool:
    user_id = str(member.id)
    guild_id = str(member.guild.id)
    op = OP_EVERYONE
    global_admins = get_global_admin_ids()
    guild_admins = get_guild_admin_ids(guild_id)
    staff_role_id = get_staff_role_id(guild_id)
    if user_id in global_admins:
        op = OP_GLOBAL_ADMIN
    elif guild_admins and user_id in guild_admins:
        op = OP_GUILD_ADMIN
    elif staff_role_id and staff_role_id != 'None' and any(str(r.id) == staff_role_id for r in member.roles):
        op = OP_STAFF
    elif len([r for r in member.roles if r.name != '@everyone']) > 0:
        op = OP_HAS_ROLE
    return op >= required_op
