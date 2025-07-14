# Unity/index.py
"""
Unity モジュール基盤: Base型・登録APIを利用したSystem/Module管理
"""
import importlib
import glob
import os
import threading
import time
import asyncio
from Unity.Base import unity_registry, SystemBase




# --- Module自動ロード&登録 ---
def load_modules():
    module_dir = os.path.join(os.path.dirname(__file__), "Module")
    if not os.path.isdir(module_dir):
        return
    py_files = glob.glob(os.path.join(module_dir, "*.py"))
    for file in py_files:
        modname = os.path.splitext(os.path.basename(file))[0]
        if modname.startswith("__"): continue
        import_path = f"Unity.Module.{modname}"
        try:
            importlib.import_module(import_path)
        except Exception as e:
            print(f"[Unity] モジュール {import_path} のimport失敗: {e}")
load_modules()

# エイリアス
system = unity_registry.system
afterEvent = unity_registry.events
