import os
import requests
import json
import sys

def fetch_and_merge_json(url, local_path="database.json"):
    key = os.environ.get("Key")
    params = {"Key": key} if key else {}
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        print(f"[ERROR] Failed to fetch: {resp.status_code} {resp.text}")
        return False
    remote_data = resp.json()
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            local_data = json.load(f)
    else:
        local_data = {}
    # マージ（remote優先でlocalに上書き）
    merged = local_data.copy()
    merged.update(remote_data)
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Merged and saved to {local_path}")
    return True

if __name__ == "__main__":
    url = "https://discord-pri1.onrender.com/database"
    fetch_and_merge_json(url)
