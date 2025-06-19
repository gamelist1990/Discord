from plugins.antiModule.spam import TEXT_SPAM_CONFIG, user_recent_messages, RECENT_MSG_COUNT, DEFAULT_TIMEOUT_DURATION, _now
from plugins.antiModule.bypass import MiniAntiBypass
from plugins.antiModule.spam import BaseSpam
import difflib
import re
from collections import deque
import discord

class TextSpam(BaseSpam):
    @staticmethod
    async def check_and_block_spam(message: discord.Message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        from plugins.antiModule.config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "text_spam"):
            return False
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        if uid not in user_recent_messages:
            user_recent_messages[uid] = deque(maxlen=RECENT_MSG_COUNT)
        user_recent_messages[uid].append((now, message.content))
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
        if len(user_recent_messages[uid]) >= 2:
            t0 = user_recent_messages[uid][-2][0]
            dt = now - t0
            if dt < TEXT_SPAM_CONFIG["rapid_post_threshold"]:
                score += TEXT_SPAM_CONFIG["rapid_post_score"]
            elif dt < TEXT_SPAM_CONFIG["fast_post_threshold"]:
                score += TEXT_SPAM_CONFIG["fast_post_score"]
        content = message.content
        if content:
            symbol_ratio = sum(1 for c in content if not c.isalnum()) / max(1, len(content))
            if symbol_ratio > TEXT_SPAM_CONFIG["high_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["high_symbol_score"]
            elif symbol_ratio > TEXT_SPAM_CONFIG["medium_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["medium_symbol_score"]
        repeated_char_match = re.search(r"(.)\1{7,}", content)
        repeated_digit_match = re.search(r"(\d)\1{7,}", content)
        uuid4_pattern = re.compile(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}")
        uuid4_matches = uuid4_pattern.findall(content)
        uuid4_count = len(uuid4_matches)
        dot_pattern = re.compile(r"(?:[a-zA-Z0-9]\.){4,}[a-zA-Z0-9_]+")
        dot_matches = dot_pattern.findall(content)
        dot_count = len(dot_matches)
        if repeated_char_match or repeated_digit_match:
            score += 0.4
        if uuid4_count >= 2:
            score += 0.5
        elif uuid4_count == 1:
            score += 0.25
        if dot_count >= 1:
            score += 0.2
        if score >= TEXT_SPAM_CONFIG["base_threshold"]:
            from plugins.antiModule.spam import spam_log_aggregator
            guild_id = message.guild.id if message.guild else None
            spam_log_aggregator.add_spam_log(guild_id, uid, "text", now)
            if guild_id and spam_log_aggregator.check_mass_spam(guild_id):
                alert_type = "mass_text"
            else:
                alert_type = "text"
            return await TextSpam.block_and_notify(
                message,
                uid,
                now,
                alert_type,
                timeout_duration,
                "テキストスパム検知による自動タイムアウト",
            )
        return False
