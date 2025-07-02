import subprocess
from datetime import datetime
import shutil
import sys
import os
from dotenv import load_dotenv  # 追加

load_dotenv()  # .envから環境変数を読み込む

def create_pull_request():
    # gh CLIが存在するかチェック
    if shutil.which("gh") is None:
        print("[WARN] gh CLIが見つかりません。pull request自動作成にはGitHub CLI (gh) が必要です。\nhttps://cli.github.com/manual/installation を参照してください。")
        sys.exit(1)
    # 現在のブランチ名取得
    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
    current_branch = result.stdout.strip()
    if current_branch == "main" or current_branch == "master":
        print("[INFO] main/masterブランチ上なのでpull requestは作成しません。")
        sys.exit(0)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pr_title = f"auto PR: {now} Render自動更新 (push失敗対応)"
    pr_body = "push失敗時の自動PRです。\n\n- Render等の自動運用用\n- 内容確認後マージしてください"
    try:
        subprocess.run([
            "gh", "pr", "create",
            "--base", "main",
            "--head", current_branch,
            "--title", pr_title,
            "--body", pr_body,
            "--fill"
        ], check=True)
        print("✔ Pull Requestを自動作成しました。")
    except subprocess.CalledProcessError as e:
        print(f"❌ PRコマンドエラー: {e}")

if __name__ == "__main__":
    try:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            print("[ERROR] GITHUB_TOKEN環境変数が必要です。環境変数を設定してください。")
            sys.exit(1)
        github_user = "Koukunn_"  # 固定値
        repo_url = "gamelist1990/Discord"  # 固定値
        subprocess.run(["git", "add", "."], check=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_message = f"auto: {now} 自動的にRenderのDBを更新しました"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        remote_url = f"https://{github_user}:{github_token}@github.com/{repo_url}.git"
        # 元のリモートURLを保存
        result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, check=True)
        original_url = result.stdout.strip()
        subprocess.run(["git", "remote", "set-url", "origin", remote_url], check=True)
        try:
            subprocess.run(["git", "push"], check=True)
            print("✔ GitHubへAPIキー認証で自動コミット＆プッシュ完了")
        finally:
            subprocess.run(["git", "remote", "set-url", "origin", original_url], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Gitコマンドエラー: {e}")
        create_pull_request()
