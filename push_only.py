import subprocess
from datetime import datetime
import sys
import os
from dotenv import load_dotenv

load_dotenv()

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
        sys.exit(1)
