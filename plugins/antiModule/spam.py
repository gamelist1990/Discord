import difflib
import asyncio
import re
import time
from datetime import timedelta
from collections import deque
from .notifier import Notifier
from .bypass import MiniAntiBypass
import discord

# スパム検知用定数・グローバル変数
SIMILARITY_THRESHOLD = 0.85
RECENT_MSG_COUNT = 5
BLOCK_DURATION = 5 * 60  # デフォルト: 5分
DEFAULT_TIMEOUT_DURATION = 5 * 60  # Discordのタイムアウト
TEXT_SPAM_CONFIG = {
    "base_threshold": 0.8,
    "high_similarity_threshold": 0.9,
    "high_similarity_score": 0.6,
    "medium_similarity_threshold": 0.75,
    "medium_similarity_score": 0.35,
    "low_similarity_threshold": 0.6,
    "low_similarity_score": 0.15,
    "rapid_post_threshold": 1.0,
    "rapid_post_score": 0.4,
    "fast_post_threshold": 2.0,
    "fast_post_score": 0.2,
    "random_text_score": 0.35,
    "repetitive_char_score": 0.4,
    "no_vowel_score": 0.3,
    "very_long_threshold": 500,
    "very_long_score": 0.3,
    "long_threshold": 300,
    "long_score": 0.15,
    "very_short_threshold": 2,
    "very_short_score": 0.25,
    "high_symbol_threshold": 0.7,
    "high_symbol_score": 0.3,
    "medium_symbol_threshold": 0.5,
    "medium_symbol_score": 0.15,
    "japanese_text_reduction": 0.2,
    "burst_count_threshold": 4,
    "burst_window": 10,
    "burst_score": 0.5,
}
user_recent_messages = {}
user_blocked_until = {}
IMAGE_SPAM_THRESHOLD = 3
IMAGE_SPAM_WINDOW = 30
user_image_timestamps = {}
MENTION_SPAM_THRESHOLD = 3
MENTION_SPAM_WINDOW = 30
user_mention_timestamps = {}
user_time_intervals = {}
TOKEN_SPAM_WINDOW = 5
TOKEN_SPAM_THRESHOLD = 3
content_token_spam_map = {}
TOKEN_SPAM_SIMILARITY_THRESHOLD = 0.85  # 類似度しきい値

def _now():
    return int(time.time())

class Spam:
    @staticmethod
    async def check_and_block_spam(message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        # AntiCheat全体が無効な場合は処理しない
        from .config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        
        # テキストスパム検知が無効な場合は処理しない
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "text_spam"):
            return False
        
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        # 履歴管理
        if uid not in user_recent_messages:
            user_recent_messages[uid] = deque(maxlen=RECENT_MSG_COUNT)
        user_recent_messages[uid].append((now, message.content))
        # 類似性判定
        recent = [c for t, c in user_recent_messages[uid] if c]
        if len(recent) < 2:
            return False
        score = 0
        for i in range(len(recent) - 1):
            s = difflib.SequenceMatcher(None, recent[i], recent[-1]).ratio()
            if s > TEXT_SPAM_CONFIG["high_similarity_threshold"]:
                score += TEXT_SPAM_CONFIG["high_similarity_score"]
            elif s > TEXT_SPAM_CONFIG["medium_similarity_threshold"]:
                score += TEXT_SPAM_CONFIG["medium_similarity_score"]
            elif s > TEXT_SPAM_CONFIG["low_similarity_threshold"]:
                score += TEXT_SPAM_CONFIG["low_similarity_score"]
        # 連投速度
        if len(user_recent_messages[uid]) >= 2:
            t0 = user_recent_messages[uid][-2][0]
            dt = now - t0
            if dt < TEXT_SPAM_CONFIG["rapid_post_threshold"]:
                score += TEXT_SPAM_CONFIG["rapid_post_score"]
            elif dt < TEXT_SPAM_CONFIG["fast_post_threshold"]:
                score += TEXT_SPAM_CONFIG["fast_post_score"]
        # 記号率
        content = message.content
        if content:
            symbol_ratio = sum(1 for c in content if not c.isalnum()) / max(1, len(content))
            if symbol_ratio > TEXT_SPAM_CONFIG["high_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["high_symbol_score"]
            elif symbol_ratio > TEXT_SPAM_CONFIG["medium_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["medium_symbol_score"]
        # 長文・短文
        if len(content) > TEXT_SPAM_CONFIG["very_long_threshold"]:
            score += TEXT_SPAM_CONFIG["very_long_score"]
        elif len(content) > TEXT_SPAM_CONFIG["long_threshold"]:
            score += TEXT_SPAM_CONFIG["long_score"]
        elif len(content) <= TEXT_SPAM_CONFIG["very_short_threshold"]:
            score += TEXT_SPAM_CONFIG["very_short_score"]
        # 日本語テキスト判定
        if re.search(r'[ぁ-んァ-ン一-龥]', content):
            score -= TEXT_SPAM_CONFIG["japanese_text_reduction"]
        # スコア判定
        if score >= TEXT_SPAM_CONFIG["base_threshold"]:
            user_blocked_until[uid] = now + BLOCK_DURATION
            await Notifier(message).purge_user_messages(alert_type="text")
            try:
                await message.author.timeout(duration=timeout_duration, reason="テキストスパム検知による自動タイムアウト")
            except Exception:
                pass
            return True
        return False

class MediaSpam:
    @staticmethod
    async def check_and_block_media_spam(message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        # AntiCheat全体が無効な場合は処理しない
        from .config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        
        # 画像スパム検知が無効な場合は処理しない
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "image_spam"):
            return False
        
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        if uid not in user_image_timestamps:
            user_image_timestamps[uid] = deque()
        # 添付ファイル・埋め込み画像
        if message.attachments or any(e.type == "image" for e in getattr(message, "embeds", [])):
            user_image_timestamps[uid].append(now)
            # 古い履歴を削除
            while user_image_timestamps[uid] and now - user_image_timestamps[uid][0] > IMAGE_SPAM_WINDOW:
                user_image_timestamps[uid].popleft()
            if len(user_image_timestamps[uid]) >= IMAGE_SPAM_THRESHOLD:
                user_blocked_until[uid] = now + BLOCK_DURATION
                await Notifier(message).purge_user_messages(alert_type="image")
                try:
                    await message.author.timeout(duration=timeout_duration, reason="画像・動画スパム検知による自動タイムアウト")
                except Exception:
                    pass
                return True
        return False

class MentionSpam:
    @staticmethod
    async def check_and_block_mention_spam(message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        # AntiCheat全体が無効な場合は処理しない
        from .config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        
        # メンションスパム検知が無効な場合は処理しない
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "mention_spam"):
            return False
        
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        if uid not in user_mention_timestamps:
            user_mention_timestamps[uid] = deque()
        if message.mentions:
            user_mention_timestamps[uid].append(now)
            while user_mention_timestamps[uid] and now - user_mention_timestamps[uid][0] > MENTION_SPAM_WINDOW:
                user_mention_timestamps[uid].popleft()
            if len(user_mention_timestamps[uid]) >= MENTION_SPAM_THRESHOLD:
                user_blocked_until[uid] = now + BLOCK_DURATION
                await Notifier(message).purge_user_messages(alert_type="mention")
                try:
                    await message.author.timeout(duration=timeout_duration, reason="メンションスパム検知による自動タイムアウト")
                except Exception:
                    pass
                return True
        return False

class TokenSpam:
    @staticmethod
    async def check_and_block_token_spam(message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        from .config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "token_spam"):
            return False
        if await MiniAntiBypass.should_bypass(message):
            return False
        now = _now()
        content = message.content
        if not content:
            return False

        # 類似度でグループ化
        matched_key = None
        for (gid, prev_content), entries in content_token_spam_map.items():
            if gid == message.guild.id:
                similarity = difflib.SequenceMatcher(None, prev_content, content).ratio()
                if similarity >= TOKEN_SPAM_SIMILARITY_THRESHOLD:
                    matched_key = (gid, prev_content)
                    break
        if matched_key is None:
            matched_key = (message.guild.id, content)
            content_token_spam_map[matched_key] = deque()
        content_token_spam_map[matched_key].append((now, message.author.id))
        # 古い履歴を削除
        while content_token_spam_map[matched_key] and now - content_token_spam_map[matched_key][0][0] > TOKEN_SPAM_WINDOW:
            content_token_spam_map[matched_key].popleft()
        # 3人以上が同一内容または高類似度内容を短時間で送信
        user_ids = set(uid for t, uid in content_token_spam_map[matched_key])
        if len(user_ids) >= TOKEN_SPAM_THRESHOLD:
            for t, uid in content_token_spam_map[matched_key]:
                user_blocked_until[uid] = now + BLOCK_DURATION
            await Notifier(message).purge_user_messages(alert_type="token")
            try:
                await message.author.timeout(duration=timeout_duration, reason="Token/Webhookスパム検知による自動タイムアウト")
            except Exception:
                pass
            return True
        return False

class TimebaseSpam:
    @staticmethod
    async def check_and_block_timebase_spam(message, min_msgs=8, var_threshold=0.15, hist_threshold=0.7, max_history=15, reset_interval=60, similarity_threshold=0.85, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        # AntiCheat全体が無効な場合は処理しない
        from .config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        
        # タイムベーススパム検知が無効な場合は処理しない
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "timebase_spam"):
            return False
        
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        if uid not in user_time_intervals:
            user_time_intervals[uid] = deque(maxlen=max_history)
        # 直近の送信間隔
        if hasattr(message, "created_at"):
            ts = int(message.created_at.timestamp())
        else:
            ts = now
        if user_time_intervals[uid]:
            interval = ts - user_time_intervals[uid][-1][0]
            user_time_intervals[uid].append((ts, interval))
        else:
            user_time_intervals[uid].append((ts, 0))
        # 一定数以上の履歴があれば分散・類似性チェック
        if len(user_time_intervals[uid]) >= min_msgs:
            intervals = [iv for t, iv in list(user_time_intervals[uid])[1:]]
            if intervals:
                mean = sum(intervals) / len(intervals)
                var = sum((iv - mean) ** 2 for iv in intervals) / len(intervals)
                # 分散が小さい（機械的な連投）
                if var < var_threshold:
                    user_blocked_until[uid] = now + BLOCK_DURATION
                    await Notifier(message).purge_user_messages(alert_type="timebase")
                    try:
                        await message.author.timeout(duration=timeout_duration, reason="タイムベーススパム検知による自動タイムアウト")
                    except Exception:
                        pass
                    return True
        return False

class Block:
    @staticmethod
    async def is_user_blocked(message):
        uid = message.author.id
        now = _now()
        if uid in user_blocked_until and user_blocked_until[uid] > now:
            return True
        return False
    @staticmethod
    async def handle_unblock(user_id):
        if user_id in user_blocked_until:
            del user_blocked_until[user_id]

class Griefing:
    @staticmethod
    async def handle_griefing(message, alert_type="text"):
        # 通知や管理者へのEmbed送信など（省略可、必要に応じて拡張）
        pass

class GuildConfig:
    @staticmethod
    async def save_guild_json(guild, key, value):
        import json
        from DataBase import set_guild_data, get_guild_data
        guild_id = guild.id if hasattr(guild, "id") else guild
        data = get_guild_data(guild_id)
        data[key] = value
        set_guild_data(guild_id, data)

    @staticmethod
    async def load_guild_json(guild, key):
        from DataBase import get_guild_data
        guild_id = guild.id if hasattr(guild, "id") else guild
        data = get_guild_data(guild_id)
        return data.get(key)

