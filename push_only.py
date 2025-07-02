import os
import base64
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "gamelist1990/Discord"
FILE_PATH = "database.json"
BRANCH = "main"
COMMIT_MESSAGE = f"auto: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WebAPIでdatabase.jsonを更新"

if not GITHUB_TOKEN:
    print("[ERROR] GITHUB_TOKEN環境変数が必要です。")
    exit(1)

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
    response_data = r.json()
    sha = response_data["sha"]
    current_content = response_data["content"]
    print(f"[INFO] 取得したSHA: {sha}")
    print(f"[INFO] 現在のGitHubファイル内容を取得完了")
elif r.status_code == 404:
    print(f"[INFO] ファイルがGitHub上に存在しません。新規作成します。")
    sha = None
    current_content = None
else:
    print(f"[ERROR] GitHub APIからファイル情報の取得に失敗: {r.status_code} - {r.text}")
    exit(1)

# 内容の比較
if current_content is not None:
    print(f"[INFO] ローカルファイルとGitHubファイルの内容を比較中...")
    # GitHubから取得した内容は改行文字が含まれている可能性があるため、それを除去して比較
    github_content_cleaned = current_content.replace('\n', '')
    if content == github_content_cleaned:
        print(f"[INFO] ファイル内容に変更がありません。更新をスキップします。")
        print("✔ ファイル内容は最新の状態です")
        exit(0)
    else:
        print(f"[INFO] ファイル内容に変更が検出されました。更新を続行します。")
else:
    print(f"[INFO] 新規ファイルのため、内容比較をスキップして作成を続行します。")

# ファイルを更新
print(f"[INFO] ファイルを更新中... (commit message: '{COMMIT_MESSAGE}')")
data = {
    "message": COMMIT_MESSAGE,
    "content": content,
    "branch": BRANCH
}
# 既存ファイルの場合のみSHAを追加
if sha is not None:
    data["sha"] = sha
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