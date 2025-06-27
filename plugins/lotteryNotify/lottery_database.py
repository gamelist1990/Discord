"""
抽選通知システム専用のデータベース管理機能
DataBase.pyのカスタムデータベース機能を使用して、抽選特化の関数を提供
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Optional, Any

# DataBase.pyをインポート
from DataBase import (
    get_custom_data, set_custom_data, update_custom_data, 
    get_custom_value, delete_custom_data, has_custom_data,
    backup_custom_db, get_custom_db_stats
)

class LotteryDatabase:
    """抽選通知システム専用のデータベース管理クラス - 単一lottery.jsonファイル使用"""
    
    # 統一データベース名
    LOTTERY_DB_NAME = "lottery"
    
    def __init__(self, module_name: Optional[str] = None):
        self.module_name = module_name
        # 全てのモジュールで同じlottery.jsonを使用
        self.db_name = self.LOTTERY_DB_NAME
    
    # === ギルド設定管理（システム全体用） ===
    
    def get_all_guild_settings(self) -> Dict[str, str]:
        """全てのギルド設定を取得"""
        return get_custom_data(self.db_name, "guild_settings")
    
    def set_guild_setting(self, guild_id: str, channel_id: str) -> bool:
        """ギルドの通知チャンネルを設定"""
        try:
            guild_settings = get_custom_data(self.db_name, "guild_settings")
            guild_settings[str(guild_id)] = str(channel_id)
            set_custom_data(self.db_name, "guild_settings", guild_settings)
            return True
        except Exception as e:
            print(f"[LotteryDatabase] ギルド設定保存エラー: {e}")
            return False
    
    def get_guild_setting(self, guild_id: str) -> Optional[str]:
        """ギルドの通知チャンネルIDを取得"""
        guild_settings = get_custom_data(self.db_name, "guild_settings")
        return guild_settings.get(str(guild_id))
    
    def remove_guild_setting(self, guild_id: str) -> bool:
        """ギルドの設定を削除"""
        try:
            guild_settings = get_custom_data(self.db_name, "guild_settings")
            if str(guild_id) in guild_settings:
                del guild_settings[str(guild_id)]
                set_custom_data(self.db_name, "guild_settings", guild_settings)
                return True
            return False
        except Exception as e:
            print(f"[LotteryDatabase] ギルド設定削除エラー: {e}")
            return False
    
    def has_guild_setting(self, guild_id: str) -> bool:
        """ギルドの設定が存在するかチェック"""
        guild_settings = get_custom_data(self.db_name, "guild_settings")
        return str(guild_id) in guild_settings

    # === 基本的な状態管理（モジュール専用） ===
    
    def get_state(self, key: Optional[str] = None, default: Any = None) -> Any:
        """抽選モジュールの状態を取得"""
        if self.module_name is None:
            raise ValueError("モジュール名が設定されていません。状態管理にはmodule_nameが必要です。")
            
        module_data = get_custom_data(self.db_name, self.module_name)
        state_data = module_data.get("state", {})
        
        if key is None:
            return state_data
        return state_data.get(key, default)
    
    def save_state(self, key: str, value: Any) -> None:
        """抽選モジュールの状態を保存"""
        if self.module_name is None:
            raise ValueError("モジュール名が設定されていません。状態管理にはmodule_nameが必要です。")
            
        # モジュールデータを取得
        module_data = get_custom_data(self.db_name, self.module_name)
        state_data = module_data.setdefault("state", {})
        state_data[key] = value
        
        # 更新されたモジュールデータを保存
        set_custom_data(self.db_name, self.module_name, module_data)
    
    def delete_state(self, key: str) -> None:
        """抽選モジュールの特定の状態を削除"""
        if self.module_name is None:
            raise ValueError("モジュール名が設定されていません。状態管理にはmodule_nameが必要です。")
            
        module_data = get_custom_data(self.db_name, self.module_name)
        state_data = module_data.get("state", {})
        if key in state_data:
            del state_data[key]
            module_data["state"] = state_data
            set_custom_data(self.db_name, self.module_name, module_data)
    
    # === チェック済みアイテム管理 ===
    
    def get_seen_items(self) -> List[str]:
        """既にチェック済みのアイテム一覧を取得"""
        if self.module_name is None:
            raise ValueError("モジュール名が設定されていません。")
        return self.get_state("seen_items", [])
    
    def add_seen_item(self, item_id: str) -> None:
        """チェック済みのアイテムを追加"""
        if self.module_name is None:
            raise ValueError("モジュール名が設定されていません。")
        seen_items = self.get_seen_items()
        if item_id not in seen_items:
            seen_items.append(item_id)
            self.save_state("seen_items", seen_items)
    
    def add_seen_items(self, item_ids: List[str]) -> None:
        """複数のチェック済みアイテムを一括追加"""
        seen_items = self.get_seen_items()
        new_items = [item_id for item_id in item_ids if item_id not in seen_items]
        if new_items:
            seen_items.extend(new_items)
            self.save_state("seen_items", seen_items)
    
    def is_item_seen(self, item_id: str) -> bool:
        """アイテムが既にチェック済みかどうかを確認"""
        return item_id in self.get_seen_items()
    
    def remove_seen_item(self, item_id: str) -> None:
        """チェック済みアイテムから削除"""
        seen_items = self.get_seen_items()
        if item_id in seen_items:
            seen_items.remove(item_id)
            self.save_state("seen_items", seen_items)
    
    def clear_seen_items(self) -> None:
        """チェック済みアイテムを全て削除"""
        self.save_state("seen_items", [])
    
    # === チェック時刻管理 ===
    
    def set_last_check(self, timestamp: Optional[datetime] = None) -> None:
        """最後のチェック時刻を記録"""
        if timestamp is None:
            timestamp = datetime.now()
        self.save_state("last_check", timestamp.isoformat())
    
    def get_last_check(self) -> Optional[datetime]:
        """最後のチェック時刻を取得"""
        last_check_str = self.get_state("last_check")
        if last_check_str:
            try:
                return datetime.fromisoformat(last_check_str)
            except ValueError:
                return None
        return None
    
    # === 商品情報管理 ===
    
    def save_product_info(self, product_id: str, product_data: Dict) -> None:
        """商品情報を保存"""
        module_data = get_custom_data(self.db_name, self.module_name)
        products = module_data.setdefault("products", {})
        products[product_id] = {
            **product_data,
            "saved_at": datetime.now().isoformat()
        }
        module_data["products"] = products
        set_custom_data(self.db_name, self.module_name, module_data)
    
    def get_product_info(self, product_id: str) -> Optional[Dict]:
        """商品情報を取得"""
        module_data = get_custom_data(self.db_name, self.module_name)
        products = module_data.get("products", {})
        return products.get(product_id)
    
    def get_all_products(self) -> Dict[str, Dict]:
        """全ての商品情報を取得"""
        module_data = get_custom_data(self.db_name, self.module_name)
        return module_data.get("products", {})
    
    def delete_product_info(self, product_id: str) -> None:
        """商品情報を削除"""
        module_data = get_custom_data(self.db_name, self.module_name)
        products = module_data.get("products", {})
        if product_id in products:
            del products[product_id]
            module_data["products"] = products
            set_custom_data(self.db_name, self.module_name, module_data)
    
    # === 設定管理 ===
    
    def save_config(self, config_key: str, config_value: Any) -> None:
        """設定を保存"""
        module_data = get_custom_data(self.db_name, self.module_name)
        config_data = module_data.setdefault("config", {})
        config_data[config_key] = config_value
        module_data["config"] = config_data
        set_custom_data(self.db_name, self.module_name, module_data)
    
    def get_config(self, config_key: str, default: Any = None) -> Any:
        """設定を取得"""
        module_data = get_custom_data(self.db_name, self.module_name)
        config_data = module_data.get("config", {})
        return config_data.get(config_key, default)
    
    def get_all_config(self) -> Dict:
        """全ての設定を取得"""
        module_data = get_custom_data(self.db_name, self.module_name)
        return module_data.get("config", {})
    
    # === 統計・履歴管理 ===
    
    def add_check_log(self, found_count: int, notification_count: int, error: Optional[str] = None) -> None:
        """チェック履歴を記録"""
        module_data = get_custom_data(self.db_name, self.module_name)
        logs = module_data.setdefault("logs", [])
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "found_count": found_count,
            "notification_count": notification_count,
            "error": error
        }
        logs.append(log_entry)
        
        # 最新100件のみ保持
        if len(logs) > 100:
            logs = logs[-100:]
        
        module_data["logs"] = logs
        set_custom_data(self.db_name, self.module_name, module_data)
    
    def get_check_logs(self, limit: int = 10) -> List[Dict]:
        """チェック履歴を取得"""
        module_data = get_custom_data(self.db_name, self.module_name)
        logs = module_data.get("logs", [])
        return logs[-limit:] if logs else []
    
    def get_stats(self) -> Dict:
        """統計情報を取得"""
        module_data = get_custom_data(self.db_name, self.module_name)
        logs = module_data.get("logs", [])
        seen_items = self.get_seen_items()
        last_check = self.get_last_check()
        
        total_checks = len(logs)
        total_found = sum(log.get("found_count", 0) for log in logs)
        total_notifications = sum(log.get("notification_count", 0) for log in logs)
        error_count = sum(1 for log in logs if log.get("error"))
        
        return {
            "module_name": self.module_name,
            "total_checks": total_checks,
            "total_found": total_found,
            "total_notifications": total_notifications,
            "error_count": error_count,
            "seen_items_count": len(seen_items),
            "last_check": last_check.isoformat() if last_check else None,
            "success_rate": (total_checks - error_count) / total_checks if total_checks > 0 else 0
        }
    
    # === メンテナンス機能 ===
    
    def backup(self) -> None:
        """データベースのバックアップを作成"""
        backup_custom_db(self.db_name)
    
    def clear_all_data(self) -> None:
        """全てのデータを削除"""
        delete_custom_data(self.db_name, "state")
        delete_custom_data(self.db_name, "products")
        delete_custom_data(self.db_name, "config")
        delete_custom_data(self.db_name, "logs")
    
    def get_database_info(self) -> Dict:
        """データベース情報を取得"""
        return get_custom_db_stats(self.db_name)
    
    # === 便利な複合機能 ===
    
    def filter_new_items(self, items: List[Dict], id_key: str = "id") -> List[Dict]:
        """新しいアイテムのみをフィルタリング"""
        seen_items = set(self.get_seen_items())
        new_items = []
        
        for item in items:
            item_id = item.get(id_key)
            if item_id and item_id not in seen_items:
                new_items.append(item)
        
        return new_items
    
    def process_check_result(self, all_items: List[Dict], new_items: List[Dict], 
                           id_key: str = "id", error: Optional[str] = None) -> None:
        """チェック結果を処理（見つかったアイテムを記録、ログを追加）"""
        # 新しいアイテムをチェック済みに追加
        if new_items:
            new_ids = [item.get(id_key) for item in new_items if item.get(id_key)]
            # Noneを除去してstrのリストにする
            valid_ids = [item_id for item_id in new_ids if item_id is not None]
            if valid_ids:
                self.add_seen_items(valid_ids)
        
        # チェック時刻を更新
        self.set_last_check()
        
        # ログを記録
        self.add_check_log(
            found_count=len(all_items),
            notification_count=len(new_items),
            error=error
        )


# === グローバル関数（後方互換性のため） ===

def get_lottery_database(module_name: str) -> LotteryDatabase:
    """指定されたモジュール名の抽選データベースインスタンスを取得"""
    return LotteryDatabase(module_name)

# 旧形式の関数（後方互換性のため）
def get_lottery_state(module_name: str, key: Optional[str] = None, default: Any = None) -> Any:
    """【非推奨】get_lottery_database(module_name).get_state()を使用してください"""
    db = LotteryDatabase(module_name)
    return db.get_state(key, default)

def save_lottery_state(module_name: str, key: str, value: Any) -> None:
    """【非推奨】get_lottery_database(module_name).save_state()を使用してください"""
    db = LotteryDatabase(module_name)
    db.save_state(key, value)

def get_lottery_seen_items(module_name: str) -> List[str]:
    """【非推奨】get_lottery_database(module_name).get_seen_items()を使用してください"""
    db = LotteryDatabase(module_name)
    return db.get_seen_items()

def add_lottery_seen_item(module_name: str, item_id: str) -> None:
    """【非推奨】get_lottery_database(module_name).add_seen_item()を使用してください"""
    db = LotteryDatabase(module_name)
    db.add_seen_item(item_id)

def is_lottery_item_seen(module_name: str, item_id: str) -> bool:
    """【非推奨】get_lottery_database(module_name).is_item_seen()を使用してください"""
    db = LotteryDatabase(module_name)
    return db.is_item_seen(item_id)

def set_lottery_last_check(module_name: str) -> None:
    """【非推奨】get_lottery_database(module_name).set_last_check()を使用してください"""
    db = LotteryDatabase(module_name)
    db.set_last_check()

def get_lottery_last_check(module_name: str) -> Optional[datetime]:
    """【非推奨】get_lottery_database(module_name).get_last_check()を使用してください"""
    db = LotteryDatabase(module_name)
    return db.get_last_check()

# === 統一データベース用の便利メソッド ===

def get_all_lottery_modules() -> List[str]:
    """lottery.jsonに登録されているすべてのモジュール名を取得"""
    all_data = get_custom_data("lottery")
    return list(all_data.keys())

def get_lottery_overview() -> Dict[str, Dict]:
    """全モジュールの概要情報を取得"""
    modules = get_all_lottery_modules()
    overview = {}
    
    for module_name in modules:
        db = LotteryDatabase(module_name)
        stats = db.get_stats()
        overview[module_name] = {
            "last_check": db.get_last_check(),
            "seen_items_count": len(db.get_seen_items()),
            "total_checks": stats.get("total_checks", 0),
            "total_notifications": stats.get("total_notifications", 0),
            "error_count": stats.get("error_count", 0)
        }
    
    return overview

def cleanup_old_lottery_databases() -> List[str]:
    """古い個別データベースファイルをクリーンアップ"""
    import os
    import sys
    
    # DataBase.pyがある場所（プロジェクトルート）を取得
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    cleaned_files = []
    for file in os.listdir(root_dir):
        if file.startswith('lottery_') and file.endswith('.json'):
            old_file_path = os.path.join(root_dir, file)
            try:
                os.remove(old_file_path)
                cleaned_files.append(file)
            except Exception as e:
                print(f"ファイル削除エラー: {file} - {e}")
    
    return cleaned_files
