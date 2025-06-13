import os
import json
import shutil
from threading import Lock
from datetime import datetime
import threading
import time
import discord
import asyncio

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.json")
DB_BACKUP_FILE = os.path.join(BASE_DIR, "database.json.bak")
_db_lock = Lock()

def _load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with _db_lock, open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # バックアップから復元を試みる
        if os.path.exists(DB_BACKUP_FILE):
            try:
                with open(DB_BACKUP_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

def _save_db(data):
    # 保存前にバックアップを作成
    if os.path.exists(DB_FILE):
        try:
            shutil.copy2(DB_FILE, DB_BACKUP_FILE)
        except Exception:
            pass
    with _db_lock, open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ギルド毎のデータ管理機能
def get_guild_data(guild_id):
    """指定されたギルドのデータを取得"""
    db = _load_db()
    return db.get(str(guild_id), {})

def set_guild_data(guild_id, data):
    """指定されたギルドのデータを保存"""
    db = _load_db()
    db[str(guild_id)] = data
    _save_db(db)

def update_guild_data(guild_id, key, value):
    """指定されたギルドの特定のキーのデータを更新"""
    db = _load_db()
    guild_data = db.setdefault(str(guild_id), {})
    guild_data[key] = value
    _save_db(db)

def get_guild_value(guild_id, key, default=None):
    """指定されたギルドの特定のキーの値を取得"""
    guild_data = get_guild_data(guild_id)
    return guild_data.get(key, default)

def delete_guild_data(guild_id):
    """指定されたギルドのデータを削除"""
    db = _load_db()
    if str(guild_id) in db:
        del db[str(guild_id)]
        _save_db(db)

def get_all_guilds():
    """全てのギルドIDのリストを取得"""
    db = _load_db()
    return list(db.keys())

def has_guild_data(guild_id):
    """指定されたギルドのデータが存在するかチェック"""
    db = _load_db()
    return str(guild_id) in db

# チャンネル設定管理機能
def get_channel_config(guild_id, channel_id):
    """指定されたチャンネルの設定を取得"""
    guild_data = get_guild_data(guild_id)
    channels = guild_data.get("channels", {})
    return channels.get(str(channel_id), {})

def set_channel_config(guild_id, channel_id, config):
    """指定されたチャンネルの設定を保存"""
    db = _load_db()
    guild_data = db.setdefault(str(guild_id), {})
    channels = guild_data.setdefault("channels", {})
    channels[str(channel_id)] = config
    _save_db(db)

def update_channel_config(guild_id, channel_id, key, value):
    """指定されたチャンネルの特定の設定を更新"""
    config = get_channel_config(guild_id, channel_id)
    config[key] = value
    set_channel_config(guild_id, channel_id, config)

def get_channel_value(guild_id, channel_id, key, default=None):
    """指定されたチャンネルの特定の設定値を取得"""
    config = get_channel_config(guild_id, channel_id)
    return config.get(key, default)

def delete_channel_config(guild_id, channel_id):
    """指定されたチャンネルの設定を削除"""
    db = _load_db()
    guild_data = db.get(str(guild_id), {})
    channels = guild_data.get("channels", {})
    if str(channel_id) in channels:
        del channels[str(channel_id)]
        _save_db(db)

# --- GuildDatabaseカテゴリ管理 ---
class GuildDatabase:
    CATEGORY_NAME = "📃｜DataBase"
    CHANNEL_PREFIX = "db-"
    RATE_LIMIT_SECONDS = 2  # チャンネル作成・削除の最小間隔
    _last_action = {}

    @classmethod
    async def ensure_category(cls, guild: discord.Guild):
        category = discord.utils.get(guild.categories, name=cls.CATEGORY_NAME)
        bot_member = guild.me
        if not category:
            overwrites = {}
            if guild.default_role is not None:
                overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            category = await guild.create_category(
                name=cls.CATEGORY_NAME,
                overwrites=overwrites,  # type: ignore
                reason="GuildDatabaseカテゴリ自動作成"
            )
            # botに権限を付与
            if bot_member:
                await category.set_permissions(bot_member, view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True)
        else:
            # 権限を再設定
            overwrites = dict(category.overwrites)
            overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            await category.edit(overwrites=overwrites, reason="GuildDatabaseカテゴリ権限修正")
            if bot_member:
                await category.set_permissions(bot_member, view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True)
        return category

    @classmethod
    async def clearAll(cls, guild: discord.Guild):
        """カテゴリ内の全チャンネルを削除（RateLimit対策あり）"""
        category = await cls.ensure_category(guild)
        now = asyncio.get_event_loop().time()
        last = cls._last_action.get(guild.id, 0)
        if now - last < cls.RATE_LIMIT_SECONDS:
            await asyncio.sleep(cls.RATE_LIMIT_SECONDS - (now - last))
        for channel in list(category.channels):
            try:
                await channel.delete(reason="GuildDatabase全削除")
                await asyncio.sleep(cls.RATE_LIMIT_SECONDS)
            except Exception:
                pass
        cls._last_action[guild.id] = asyncio.get_event_loop().time()

    @classmethod
    async def create_db_channel(cls, guild: discord.Guild, name: str, content: str = ""):
        """カテゴリ内に新しいDBチャンネルを作成（RateLimit対策あり）"""
        category = await cls.ensure_category(guild)
        now = asyncio.get_event_loop().time()
        last = cls._last_action.get(guild.id, 0)
        if now - last < cls.RATE_LIMIT_SECONDS:
            await asyncio.sleep(cls.RATE_LIMIT_SECONDS - (now - last))
        channel = await guild.create_text_channel(
            name=f"{cls.CHANNEL_PREFIX}{name}",
            category=category,
            reason="GuildDatabaseチャンネル自動生成",
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True)
            }
        )
        if content:
            try:
                await channel.send(content)
            except Exception:
                pass
        cls._last_action[guild.id] = asyncio.get_event_loop().time()
        return channel

    @classmethod
    async def get_db_channels(cls, guild: discord.Guild):
        category = await cls.ensure_category(guild)
        return [ch for ch in category.channels if isinstance(ch, discord.TextChannel) and ch.name.startswith(cls.CHANNEL_PREFIX)]

# === APIキー管理 ===
API_KEY_DB_KEY = "api_keys"
_db_lock = Lock()

# APIキーの期限切れ自動削除ループ
_cleanup_thread = None
def start_api_key_cleanup_loop(interval_sec=60):
    global _cleanup_thread
    if _cleanup_thread and _cleanup_thread.is_alive():
        return  # すでに動作中
    def cleanup_loop():
        while True:
            try:
                db = _load_db()
                api_keys = db.get(API_KEY_DB_KEY, {})
                now = datetime.now()
                to_delete = []
                for k, v in list(api_keys.items()):
                    try:
                        expire = v["expire"]
                        if isinstance(expire, str):
                            expire = datetime.strptime(expire, "%Y-%m-%dT%H:%M:%S")
                        if now > expire:
                            to_delete.append(k)
                    except Exception:
                        continue
                for k in to_delete:
                    del api_keys[k]
                if to_delete:
                    db[API_KEY_DB_KEY] = api_keys
                    _save_db(db)
            except Exception:
                pass
            time.sleep(interval_sec)
    _cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    _cleanup_thread.start()

def save_api_key(user_id, api_key, expire):
    db = _load_db()
    api_keys = db.setdefault(API_KEY_DB_KEY, {})
    api_keys[api_key] = {
        "user_id": user_id,
        "expire": expire.strftime("%Y-%m-%dT%H:%M:%S")
    }
    _save_db(db)

def get_api_key(api_key):
    db = _load_db()
    api_keys = db.get(API_KEY_DB_KEY, {})
    info = api_keys.get(api_key)
    if not info:
        return None
    # 期限をdatetime型で返す
    info = info.copy()
    info["expire"] = datetime.strptime(info["expire"], "%Y-%m-%dT%H:%M:%S")
    return info

def delete_api_key(api_key):
    db = _load_db()
    api_keys = db.get(API_KEY_DB_KEY, {})
    if api_key in api_keys:
        del api_keys[api_key]
        _save_db(db)

async def ensure_guild_database_category(guild: discord.Guild, bot_user: discord.Member, role_name: str = "DataBaseAccess"):
    """
    ギルドに専用カテゴリ「📃｜DataBase」とアクセス用ロールを作成し、botに付与。
    カテゴリの閲覧権限をそのロールのみに設定し、通知を全てoffにする。
    戻り値: (category, role)
    """
    # ロール作成または取得
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name, reason="DataBaseアクセス用自動ロール")
    # botにロールを付与
    if role not in bot_user.roles:
        await bot_user.add_roles(role, reason="DataBaseアクセス用ロール自動付与")
    # カテゴリ作成または取得
    category = discord.utils.get(guild.categories, name="📃｜DataBase")
    if not category:
        overwrites = {}
        default_role_obj = discord.utils.get(guild.roles, id=guild.default_role.id)
        role_obj = discord.utils.get(guild.roles, id=role.id)
        if default_role_obj is not None:
            overwrites[default_role_obj] = discord.PermissionOverwrite(view_channel=False)
        if role_obj is not None:
            overwrites[role_obj] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        category = await guild.create_category(name="📃｜DataBase", overwrites=overwrites, reason="DataBase専用カテゴリ自動作成")
    else:
        # 既存カテゴリの権限を修正 
        overwrites = category.overwrites
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        await category.edit(overwrites=overwrites, reason="DataBaseカテゴリ権限修正")
    # 通知設定はAPIから直接は変更不可。必要なら案内メッセージを送信
    for channel in category.channels:
        try:
            if isinstance(channel, discord.TextChannel):
                await channel.edit(slowmode_delay=0, reason="DataBaseカテゴリ通知抑制")
        except Exception:
            pass
    return category, role


