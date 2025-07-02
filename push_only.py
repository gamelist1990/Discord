import subprocess
from datetime import datetime

if __name__ == "__main__":
    try:
        subprocess.run(["git", "add", "."], check=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        commit_message = f"auto: {now} コード整理・通知Bot軽量化・Embed/URLモード統合"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✔ GitHubへ自動コミット＆プッシュ完了")
    except subprocess.CalledProcessError as e:
        print(f"❌ Gitコマンドエラー: {e}")
