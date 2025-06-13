# 補助関数・共通ユーティリティ

import time
import re
import difflib

def now():
    """現在のUNIXタイムスタンプ（int秒）"""
    return int(time.time())

def similarity(a, b):
    """2つの文字列の類似度（0.0〜1.0）"""
    return difflib.SequenceMatcher(None, a, b).ratio()

def is_japanese(text):
    """日本語文字が含まれているか判定"""
    return bool(re.search(r'[ぁ-んァ-ン一-龥]', text))

def parse_duration(s):
    """例: '1m', '2h', '3d', '10s' → 秒数(int)"""
    m = re.match(r"(\d+)([smhd])", s)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == 's':
        return n
    if unit == 'm':
        return n * 60
    if unit == 'h':
        return n * 3600
    if unit == 'd':
        return n * 86400
    return None

def mention_to_id(mention):
    """<@1234567890> → 1234567890"""
    m = re.match(r'<@!?(\d+)>', mention)
    return int(m.group(1)) if m else None

def get_user_display_name(user):
    """ユーザーの表示名（ニックネーム優先）"""
    return getattr(user, 'display_name', None) or getattr(user, 'name', None) or str(user)

# 他にも必要なユーティリティがあればここに追加

