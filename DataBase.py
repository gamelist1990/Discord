import os
import json
from threading import Lock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.json")
_db_lock = Lock()

def _load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with _db_lock, open(DB_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def _save_db(data):
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

# チャンネルトピックJSON管理機能（最大1000文字対応）
def create_topic_json_base():
    """チャンネルトピック用の基本JSON構造を作成"""
    return {
        "v": 1,  # バージョン（短縮キー）
        "d": {}  # データ（短縮キー）
    }

def encode_topic_json(data, max_length=1000):
    """データをチャンネルトピック用の圧縮JSONに変換"""
    try:
        # 基本構造にデータを追加
        topic_data = create_topic_json_base()
        topic_data["d"] = data
        
        # JSON文字列に変換（スペースなし）
        json_str = json.dumps(topic_data, ensure_ascii=False, separators=(',', ':'))
        
        # 文字数制限チェック
        if len(json_str) > max_length:
            # データが大きすぎる場合は警告
            raise ValueError(f"データが大きすぎます: {len(json_str)}文字 (上限: {max_length}文字)")
        
        return json_str
    except Exception as e:
        raise ValueError(f"JSON変換エラー: {str(e)}")

def decode_topic_json(json_str):
    """チャンネルトピックのJSONを解析してデータを取得"""
    try:
        if not json_str or json_str.strip() == "":
            return {}
        
        # JSON解析
        data = json.loads(json_str)
        
        # バージョンチェック
        if not isinstance(data, dict) or "v" not in data:
            # 古い形式またはJSON以外の場合は空のデータを返す
            return {}
        
        # データを取得
        return data.get("d", {})
    except json.JSONDecodeError:
        # JSON形式でない場合は空のデータを返す
        return {}
    except Exception:
        return {}

def update_topic_data(current_topic, key, value, max_length=1000):
    """チャンネルトピックの特定のキーを更新"""
    try:
        # 現在のデータを取得
        current_data = decode_topic_json(current_topic)
        
        # データを更新
        current_data[key] = value
        
        # 新しいJSON文字列を作成
        return encode_topic_json(current_data, max_length)
    except Exception as e:
        raise ValueError(f"トピック更新エラー: {str(e)}")

def get_topic_value(topic_json, key, default=None):
    """チャンネルトピックから特定のキーの値を取得"""
    try:
        data = decode_topic_json(topic_json)
        return data.get(key, default)
    except Exception:
        return default

def remove_topic_key(current_topic, key, max_length=1000):
    """チャンネルトピックから特定のキーを削除"""
    try:
        # 現在のデータを取得
        current_data = decode_topic_json(current_topic)
        
        # キーが存在する場合は削除
        if key in current_data:
            del current_data[key]
        
        # 新しいJSON文字列を作成
        return encode_topic_json(current_data, max_length)
    except Exception as e:
        raise ValueError(f"キー削除エラー: {str(e)}")

def get_topic_size(json_str):
    """チャンネルトピックのサイズを取得"""
    return len(json_str) if json_str else 0

def get_remaining_topic_space(json_str, max_length=1000):
    """チャンネルトピックの残り容量を取得"""
    current_size = get_topic_size(json_str)
    return max_length - current_size

def is_topic_data_valid(json_str, max_length=1000):
    """チャンネルトピックのデータが有効かチェック"""
    try:
        if get_topic_size(json_str) > max_length:
            return False
        decode_topic_json(json_str)  # JSON解析テスト
        return True
    except Exception:
        return False

def create_optimized_topic_data(data_dict, max_length=1000):
    """効率的なチャンネルトピックデータを作成（キー名を短縮）"""
    try:
        # よく使用されるキー名の短縮マッピング
        key_mapping = {
            "welcome_message": "wm",
            "auto_role": "ar", 
            "moderator_role": "mr",
            "log_channel": "lc",
            "prefix": "px",
            "level": "lv",
            "points": "pt",
            "last_active": "la",
            "permissions": "pm",
            "settings": "st"
        }
        
        # キー名を短縮
        optimized_data = {}
        for key, value in data_dict.items():
            short_key = key_mapping.get(key, key[:3])  # マッピングがなければ3文字に短縮
            optimized_data[short_key] = value
        
        return encode_topic_json(optimized_data, max_length)
    except Exception as e:
        raise ValueError(f"最適化エラー: {str(e)}")


