import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()
import os
import time
import requests

API_KEY = os.environ.get("Key", "test")
URL = f"https://pexsabas.onrender.com/consolelog?Key={API_KEY}"


import json

def fetch_consolelog():
    try:
        resp = requests.get(URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("log", "")
    except Exception as e:
        print(f"[ERROR] fetch failed: {e}")
        return None


def monitor_consolelog(interval=10):
    last_log_lines = []
    print(f"[INFO] Monitoring: {URL}")
    print(f"[INFO] API_KEY: {API_KEY}")
    print(f"[INFO] Fetch interval: {interval}s\n")
    try:
        print("=== New Console Log ===")
        while True:
            log = fetch_consolelog()
            if log is not None:
                log_lines = log.split("\n")
                new_start = len(last_log_lines)
                if log_lines[new_start:]:
                    for line in log_lines[new_start:]:
                        print(f"\033[92m{line}\033[0m")  
                    last_log_lines = log_lines
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[INFO] 監視を終了します")

if __name__ == "__main__":
    monitor_consolelog()
