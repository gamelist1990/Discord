import os
import json
from threading import Lock
from datetime import datetime
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dbsync")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.json")
DB_BACKUP_FILE = os.path.join(BASE_DIR, "database.json.bak")
_db_lock = Lock()

# --- グローバルDBキャッシュ管理 ---
global_db_cache = None

def load_db_cache():
    global global_db_cache
    if global_db_cache is None:
        if os.path.exists(DB_FILE):
            with _db_lock, open(DB_FILE, "r", encoding="utf-8") as f:
                global_db_cache = json.load(f)
        else:
            global_db_cache = {}
    return global_db_cache

def save_db_cache():
    global global_db_cache
    if global_db_cache is not None:
        with _db_lock, open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(global_db_cache, f, ensure_ascii=False, indent=2)

# --- 既存の_get/_save_dbをキャッシュ対応に書き換え ---
def _load_db():
    return load_db_cache()

def _save_db(data):
    global global_db_cache
    global_db_cache = data
    save_db_cache()

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
# GuildDatabaseクラスは廃止

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


