import os
import requests
import json
import sys
from dotenv import load_dotenv
from typing import Dict, Any


def deep_merge_remote_priority(local: Dict[Any, Any], remote: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    深いマージを実行（リモート優先）
    
    Args:
        local: ローカルのJSONデータ
        remote: リモートのJSONデータ
    
    Returns:
        マージされたデータ（リモート優先）
    """
    result = local.copy()
    
    for key, remote_value in remote.items():
        if key in result:
            local_value = result[key]
            # 両方が辞書の場合は再帰的にマージ
            if isinstance(local_value, dict) and isinstance(remote_value, dict):
                result[key] = deep_merge_remote_priority(local_value, remote_value)
            else:
                # リモート優先で上書き
                result[key] = remote_value
                print(f"[MERGE] Key '{key}' overwritten with remote value")
        else:
            # 新しいキーはリモートから追加
            result[key] = remote_value
            print(f"[MERGE] New key '{key}' added from remote")
    
    return result


def validate_json_structure(data: Any, source: str) -> bool:
    """
    JSONデータの構造を検証
    
    Args:
        data: 検証するデータ
        source: データソース名（ログ用）
    
    Returns:
        有効な場合True
    """
    if not isinstance(data, dict):
        print(f"[WARNING] {source} data is not a dictionary: {type(data)}")
        return False
    
    print(f"[INFO] {source} data validated: {len(data)} top-level keys")
    return True


def create_backup(file_path: str) -> str:
    """
    ファイルのバックアップを作成
    
    Args:
        file_path: バックアップするファイルパス
    
    Returns:
        バックアップファイルパス
    """
    if not os.path.exists(file_path):
        return ""
    
    backup_path = f"{file_path}.backup"
    try:
        import shutil
        shutil.copy2(file_path, backup_path)
        print(f"[INFO] Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"[WARNING] Failed to create backup: {e}")
        return ""


def fetch_and_merge_json(url, local_path="database.json", dotenv_path=".env"):
    """
    リモートJSONを取得してローカルファイルとマージ（リモート優先）
    
    Args:
        url: リモートAPIのURL
        local_path: ローカルファイルパス
        dotenv_path: .envファイルパス
    
    Returns:
        成功時True、失敗時False
    """
    # .envファイルの場所を指定して読み込む
    load_dotenv(dotenv_path)
    key = os.environ.get("Key")
    
    print(f"[INFO] Starting JSON merge process")
    print(f"[INFO] Remote URL: {url}")
    print(f"[INFO] Local file: {local_path}")
    print(f"[INFO] API Key: {'***' if key else 'None'}")
    
    # リモートデータを取得
    try:
        params = {"Key": key} if key else {}
        print(f"[INFO] Fetching remote data...")
        resp = requests.get(url, params=params, timeout=30)
        
        if resp.status_code != 200:
            print(f"[ERROR] HTTP {resp.status_code}: {resp.text}")
            return False
        
        # レスポンスがJSONかチェック
        try:
            response_data = resp.json()
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON response: {e}")
            print(f"[ERROR] Response text: {resp.text[:500]}...")
            return False
        
        # レスポンス構造を確認
        if isinstance(response_data, dict) and 'data' in response_data:
            # API形式のレスポンス（{ success: true, data: {...} }）
            remote_data = response_data.get('data', {})
            print(f"[INFO] Extracted data from API response")
        else:
            # 直接JSON形式のレスポンス
            remote_data = response_data
        
        if not validate_json_structure(remote_data, "Remote"):
            print(f"[ERROR] Invalid remote data structure")
            return False
        
        print(f"[INFO] Remote data fetched successfully: {len(remote_data)} keys")
        
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Request failed: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error during fetch: {e}")
        return False
    
    # ローカルデータを読み込み
    local_data = {}
    if os.path.exists(local_path):
        try:
            print(f"[INFO] Loading local data from {local_path}")
            with open(local_path, "r", encoding="utf-8") as f:
                local_data = json.load(f)
            
            if not validate_json_structure(local_data, "Local"):
                print(f"[WARNING] Local data structure invalid, using empty dict")
                local_data = {}
            else:
                print(f"[INFO] Local data loaded successfully: {len(local_data)} keys")
                
        except json.JSONDecodeError as e:
            print(f"[ERROR] Local JSON decode error: {e}")
            print(f"[WARNING] Using empty local data")
            local_data = {}
        except Exception as e:
            print(f"[ERROR] Failed to read local file: {e}")
            print(f"[WARNING] Using empty local data")
            local_data = {}
    else:
        print(f"[INFO] Local file does not exist, starting with empty data")
    
    # バックアップ作成
    backup_path = create_backup(local_path)
    
    # 深いマージを実行（リモート優先）
    print(f"[INFO] Starting deep merge (remote priority)...")
    try:
        merged_data = deep_merge_remote_priority(local_data, remote_data)
        print(f"[INFO] Merge completed: {len(merged_data)} total keys")
        
        # マージ結果の統計
        local_keys = set(local_data.keys()) if isinstance(local_data, dict) else set()
        remote_keys = set(remote_data.keys()) if isinstance(remote_data, dict) else set()
        merged_keys = set(merged_data.keys())
        
        new_keys = remote_keys - local_keys
        updated_keys = remote_keys & local_keys
        preserved_keys = local_keys - remote_keys
        
        print(f"[STATS] New keys from remote: {len(new_keys)}")
        print(f"[STATS] Updated keys from remote: {len(updated_keys)}")
        print(f"[STATS] Preserved local keys: {len(preserved_keys)}")
        
        if new_keys:
            print(f"[STATS] New keys: {list(new_keys)[:5]}{'...' if len(new_keys) > 5 else ''}")
        
    except Exception as e:
        print(f"[ERROR] Merge operation failed: {e}")
        return False
    
    # マージ結果を保存
    try:
        print(f"[INFO] Saving merged data to {local_path}")
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(merged_data, f, ensure_ascii=False, indent=2)
        
        print(f"[SUCCESS] Merged and saved to {local_path}")
        print(f"[SUCCESS] Backup available at: {backup_path}" if backup_path else "[INFO] No backup created")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to save merged data: {e}")
        # バックアップがある場合は復元を提案
        if backup_path and os.path.exists(backup_path):
            print(f"[INFO] Backup is available at {backup_path}")
        return False

def test_deep_merge():
    """深いマージ機能のテスト"""
    print("[TEST] Testing deep merge functionality...")
    
    # テストケース1: 基本的なマージ
    local = {
        "users": {"user1": {"name": "Alice", "score": 100}},
        "settings": {"theme": "dark", "lang": "ja"}
    }
    
    remote = {
        "users": {"user1": {"score": 150}, "user2": {"name": "Bob", "score": 200}},
        "settings": {"theme": "light"},
        "new_feature": {"enabled": True}
    }
    
    result = deep_merge_remote_priority(local, remote)
    
    expected_user1_score = 150  # リモート優先
    expected_theme = "light"    # リモート優先
    expected_lang = "ja"        # ローカル保持
    
    assert result["users"]["user1"]["score"] == expected_user1_score
    assert result["users"]["user1"]["name"] == "Alice"  # ローカル保持
    assert result["users"]["user2"]["name"] == "Bob"    # リモートから新規
    assert result["settings"]["theme"] == expected_theme
    assert result["settings"]["lang"] == expected_lang
    assert result["new_feature"]["enabled"] is True     # リモートから新規
    
    print("[TEST] ✅ Deep merge test passed!")
    return True


def main():
    """メイン実行関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch and merge remote JSON with local database")
    parser.add_argument("--url", default="https://discord-pri1.onrender.com/database", 
                       help="Remote API URL")
    parser.add_argument("--local", default="database.json", 
                       help="Local database file path")
    parser.add_argument("--env", default=".env", 
                       help="Environment file path")
    parser.add_argument("--test", action="store_true", 
                       help="Run tests only")
    parser.add_argument("--dry-run", action="store_true", 
                       help="Show what would be done without making changes")
    
    args = parser.parse_args()
    
    if args.test:
        try:
            test_deep_merge()
            print("[TEST] All tests passed!")
            return True
        except Exception as e:
            print(f"[TEST] Test failed: {e}")
            return False
    
    # .envのパスを明示的に指定
    dotenv_path = os.path.join(os.path.dirname(__file__), args.env)
    
    if args.dry_run:
        print("[DRY-RUN] Would fetch and merge with the following settings:")
        print(f"  Remote URL: {args.url}")
        print(f"  Local file: {args.local}")
        print(f"  Env file: {dotenv_path}")
        return True
    
    return fetch_and_merge_json(args.url, args.local, dotenv_path)


if __name__ == "__main__":
    # 引数があればmain()を、なければ従来の動作を実行
    if len(sys.argv) > 1:
        success = main()
        sys.exit(0 if success else 1)
    else:
        # 従来の動作（後方互換性）
        dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
        url = "https://pexsabas.onrender.com/database"
        success = fetch_and_merge_json(url, dotenv_path=dotenv_path)
        sys.exit(0 if success else 1)
