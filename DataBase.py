import os
import json
from threading import Lock
from datetime import datetime
import threading
import time
import logging
import requests
from dotenv import load_dotenv

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

# --- タイムスタンプ記録 ---
load_dotenv(os.path.join(BASE_DIR, ".env"))

TIMESTAMP_STARTED_KEY = "db_last_started"
TIMESTAMP_SAVED_KEY = "db_last_saved"


def record_db_timestamp(key: str):
    """database.jsonに現在時刻のタイムスタンプを記録する"""
    db = _load_db()
    db[key] = datetime.utcnow().isoformat()
    _save_db(db)


def get_db_timestamp(key: str):
    """database.jsonから指定キーのタイムスタンプを取得"""
    db = _load_db()
    return db.get(key)

# --- カスタムJSONデータベース管理 ---
custom_db_caches = {}  # {db_name: cache_data}
custom_db_locks = {}   # {db_name: Lock()}

def get_custom_db_path(db_name):
    """カスタムデータベースのファイルパスを取得"""
    return os.path.join(BASE_DIR, f"{db_name}.json")

def get_custom_db_lock(db_name):
    """カスタムデータベース用のロックを取得（なければ作成）"""
    if db_name not in custom_db_locks:
        custom_db_locks[db_name] = Lock()
    return custom_db_locks[db_name]

def load_custom_db_cache(db_name):
    """カスタムデータベースのキャッシュを読み込み"""
    global custom_db_caches
    if db_name not in custom_db_caches:
        db_file = get_custom_db_path(db_name)
        lock = get_custom_db_lock(db_name)
        if os.path.exists(db_file):
            with lock, open(db_file, "r", encoding="utf-8") as f:
                try:
                    custom_db_caches[db_name] = json.load(f)
                except json.JSONDecodeError:
                    logger.warning(f"カスタムDB {db_name} のJSONが破損しています。空のDBとして初期化します。")
                    custom_db_caches[db_name] = {}
        else:
            custom_db_caches[db_name] = {}
    return custom_db_caches[db_name]

def save_custom_db_cache(db_name):
    """カスタムデータベースのキャッシュを保存"""
    global custom_db_caches
    if db_name in custom_db_caches:
        db_file = get_custom_db_path(db_name)
        lock = get_custom_db_lock(db_name)
        with lock, open(db_file, "w", encoding="utf-8") as f:
            json.dump(custom_db_caches[db_name], f, ensure_ascii=False, indent=2)

def _load_custom_db(db_name):
    """カスタムデータベースを読み込み"""
    return load_custom_db_cache(db_name)

def _save_custom_db(db_name, data):
    """カスタムデータベースを保存"""
    global custom_db_caches
    custom_db_caches[db_name] = data
    save_custom_db_cache(db_name)

# === カスタムデータベース操作関数 ===

def get_custom_data(db_name, key=None):
    """カスタムデータベースからデータを取得"""
    db = _load_custom_db(db_name)
    if key is None:
        return db
    return db.get(str(key), {})

def set_custom_data(db_name, key, value):
    """カスタムデータベースにデータを保存"""
    db = _load_custom_db(db_name)
    db[str(key)] = value
    _save_custom_db(db_name, db)

def update_custom_data(db_name, key, sub_key, value):
    """カスタムデータベースの特定のキーの中のサブキーを更新"""
    db = _load_custom_db(db_name)
    data = db.setdefault(str(key), {})
    data[sub_key] = value
    _save_custom_db(db_name, db)

def get_custom_value(db_name, key, sub_key=None, default=None):
    """カスタムデータベースから特定の値を取得"""
    data = get_custom_data(db_name, key)
    if sub_key is None:
        return data if data else default
    return data.get(sub_key, default)

def delete_custom_data(db_name, key):
    """カスタムデータベースから特定のキーのデータを削除"""
    db = _load_custom_db(db_name)
    if str(key) in db:
        del db[str(key)]
        _save_custom_db(db_name, db)

def get_all_custom_keys(db_name):
    """カスタムデータベースの全てのキーを取得"""
    db = _load_custom_db(db_name)
    return list(db.keys())

def has_custom_data(db_name, key):
    """カスタムデータベースに指定のキーが存在するかチェック"""
    db = _load_custom_db(db_name)
    return str(key) in db

def clear_custom_db(db_name):
    """カスタムデータベースを全て削除"""
    _save_custom_db(db_name, {})

def delete_custom_db(db_name):
    """カスタムデータベースファイルを削除"""
    global custom_db_caches, custom_db_locks
    
    # キャッシュから削除
    if db_name in custom_db_caches:
        del custom_db_caches[db_name]
    
    # ロックオブジェクトを削除
    if db_name in custom_db_locks:
        del custom_db_locks[db_name]
    
    # ファイルを削除
    db_file = get_custom_db_path(db_name)
    if os.path.exists(db_file):
        os.remove(db_file)

def list_custom_databases():
    """存在するカスタムデータベース一覧を取得"""
    databases = []
    for file in os.listdir(BASE_DIR):
        if file.endswith('.json') and file != 'database.json' and file != 'database.json.bak':
            db_name = file[:-5]  # .jsonを除去
            databases.append(db_name)
    return databases



# === カスタムデータベースのバックアップ機能 ===

def backup_custom_db(db_name):
    """カスタムデータベースのバックアップを作成"""
    db_file = get_custom_db_path(db_name)
    backup_file = f"{db_file}.bak"
    
    if os.path.exists(db_file):
        import shutil
        shutil.copy2(db_file, backup_file)
        logger.info(f"カスタムDB {db_name} のバックアップを作成しました: {backup_file}")

def restore_custom_db_from_backup(db_name):
    """カスタムデータベースをバックアップから復元"""
    db_file = get_custom_db_path(db_name)
    backup_file = f"{db_file}.bak"
    
    if os.path.exists(backup_file):
        import shutil
        shutil.copy2(backup_file, db_file)
        
        # キャッシュを再読み込み
        global custom_db_caches
        if db_name in custom_db_caches:
            del custom_db_caches[db_name]
        load_custom_db_cache(db_name)
        
        logger.info(f"カスタムDB {db_name} をバックアップから復元しました")
        return True
    else:
        logger.warning(f"カスタムDB {db_name} のバックアップファイルが見つかりません")
        return False

# === カスタムデータベースの統計情報 ===

def get_custom_db_stats(db_name):
    """カスタムデータベースの統計情報を取得"""
    db = _load_custom_db(db_name)
    db_file = get_custom_db_path(db_name)
    
    stats = {
        "name": db_name,
        "keys_count": len(db),
        "file_exists": os.path.exists(db_file),
        "file_size": 0,
        "last_modified": None
    }
    
    if stats["file_exists"]:
        file_stat = os.stat(db_file)
        stats["file_size"] = file_stat.st_size
        stats["last_modified"] = datetime.fromtimestamp(file_stat.st_mtime).isoformat()
    
    return stats

def get_all_custom_db_stats():
    """全てのカスタムデータベースの統計情報を取得"""
    databases = list_custom_databases()
    stats = {}
    for db_name in databases:
        stats[db_name] = get_custom_db_stats(db_name)
    return stats


