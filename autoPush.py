import os
import sys
import subprocess
import argparse
from fetch_merge_db import fetch_and_merge_json

def get_commit_message(args):
    if args.message:
        return args.message
    print("\n==== 変更理由を入力してください（コミットメッセージ）====")
    print("例: フラグ永続化対応/データ同期/バグ修正 など")
    print("----------------------------------------------")
    msg = input("変更理由: ").strip()
    if not msg:
        msg = "auto sync: fetch_merge_db + push"
    return msg

def git_commit_and_push(commit_message):
    try:
        # 変更のある全ファイルをadd
        subprocess.run(["git", "add", "-A"], check=True)
        # 何も変更がなければコミットしない
        result = subprocess.run(["git", "diff", "--cached", "--quiet"])
        if result.returncode == 0:
            print("[INFO] コミット対象の変更がありません。スキップします。")
            return True
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("[SUCCESS] GitHubへコミット・プッシュしました。")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git操作に失敗: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="fetch_merge_db + GitHub自動コミット/プッシュ")
    parser.add_argument("--message", type=str, default=None, help="コミットメッセージを直接指定")
    parser.add_argument("--url", type=str, default="https://discord-pri1.onrender.com/database", help="リモートAPIのURL")
    parser.add_argument("--local", type=str, default="database.json", help="ローカルDBファイル")
    parser.add_argument("--env", type=str, default=".env", help=".envファイル")
    args = parser.parse_args()

    dotenv_path = os.path.join(os.path.dirname(__file__), args.env)
    print("[STEP1] fetch_merge_db 開始...")
    success = fetch_and_merge_json(args.url, args.local, dotenv_path)
    if not success:
        print("[ERROR] fetch_merge_dbに失敗しました。処理を中断します。")
        sys.exit(1)
    print("[STEP1] fetch_merge_db 完了")

    commit_message = get_commit_message(args)

    print("[STEP2] GitHubへコミット・プッシュ...")
    git_commit_and_push(commit_message)

if __name__ == "__main__":
    main()
