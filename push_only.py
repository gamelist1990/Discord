import os
import base64
import requests
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 変更点がない場合はスキップするロジックを追加
def check_changes():
    try:
        result = subprocess.run(["git", "diff", "--quiet"], check=False)
        if result.returncode == 0:
            print("[INFO] 変更点がありません。pushをスキップします。")
            return False
        else:
            print("[INFO] 変更点があります。pushを実行します。")
            return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] エラーが発生しました: {e}")
        return False

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "gamelist1990/Discord"
FILE_PATH = "database.json"
BRANCH = "main"
COMMIT_MESSAGE = f"auto: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WebAPIでdatabase.jsonを更新"

# メイン処理の開始
if __name__ == "__main__":
    if not GITHUB_TOKEN:
        print("[ERROR] GITHUB_TOKEN環境変数が必要です。")
        exit(1)
        
    if check_changes():
        # push ロジックがここで実行される
        # (既存のWebAPIでの内容更新処理を続行)
        
        print(f"[INFO] ファイル '{FILE_PATH}' をbase64エンコード中...")
        # ファイル内容をbase64エンコード
        with open(FILE_PATH, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        print(f"[INFO] エンコード完了。データ長: {len(content)} 文字")

        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json"
        }

        print(f"[INFO] 現在のファイルSHAを取得中... (branch: {BRANCH})")
        # 現在のファイルSHAを取得
        r = requests.get(
            f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}?ref={BRANCH}",
            headers=headers
        )
        print(f"[DEBUG] GET /contents レスポンス: {r.status_code} {r.text[:200]}")
        if r.status_code == 200:
            sha = r.json()["sha"]
            print(f"[INFO] 取得したSHA: {sha}")
        else:
            print(f"[ERROR] SHA取得失敗: {r.text}")
            exit(1)

        # ファイルを更新
        print(f"[INFO] ファイルを更新中... (commit message: '{COMMIT_MESSAGE}')")
        data = {
            "message": COMMIT_MESSAGE,
            "content": content,
            "branch": BRANCH,
            "sha": sha
        }
        r = requests.put(
            f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}",
            headers=headers,
            json=data
        )
        print(f"[DEBUG] PUT /contents レスポンス: {r.status_code} {r.text[:200]}")
        if r.status_code in (200, 201):
            print("✔ WebAPIでdatabase.jsonを更新しました")
        else:
            print(f"❌ エラー: {r.text}")