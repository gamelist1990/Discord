from plugins.antiModule.spam import TOKEN_SPAM_WINDOW, TOKEN_SPAM_THRESHOLD, content_token_spam_map, TOKEN_SPAM_SIMILARITY_THRESHOLD, DEFAULT_TIMEOUT_DURATION, _now, BLOCK_DURATION
from plugins.antiModule.bypass import MiniAntiBypass
from collections import deque
import difflib
import re
import discord
from plugins.antiModule.spam import BaseSpam

class TokenSpam(BaseSpam):
    @staticmethod
    async def check_and_block_token_spam(message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        from plugins.antiModule.config import AntiCheatConfig
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
        uuid4_pattern = re.compile(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}")
        uuid4_matches = uuid4_pattern.findall(content)
        uuid4_count = len(uuid4_matches)
        matched_key = None
        for (gid, prev_content), entries in content_token_spam_map.items():
            if gid == message.guild.id:
                similarity = difflib.SequenceMatcher(None, prev_content, content).ratio()
                prev_no_uuid = uuid4_pattern.sub("", prev_content)
                content_no_uuid = uuid4_pattern.sub("", content)
                similarity_no_uuid = difflib.SequenceMatcher(None, prev_no_uuid, content_no_uuid).ratio()
                if similarity >= TOKEN_SPAM_SIMILARITY_THRESHOLD or similarity_no_uuid >= 0.8:
                    matched_key = (gid, prev_content)
                    break
        if matched_key is None:
            matched_key = (message.guild.id, content)
            content_token_spam_map[matched_key] = deque()
        content_token_spam_map[matched_key].append((now, message.author.id))
        while content_token_spam_map[matched_key] and now - content_token_spam_map[matched_key][0][0] > TOKEN_SPAM_WINDOW:
            content_token_spam_map[matched_key].popleft()
        user_ids = set(uid for t, uid in content_token_spam_map[matched_key])
        is_mass_token_spam = len(user_ids) >= 3
        if len(user_ids) >= TOKEN_SPAM_THRESHOLD or uuid4_count >= 2:
            for t, uid in content_token_spam_map[matched_key]:
                from plugins.antiModule.spam import user_blocked_until
                user_blocked_until[uid] = now + BLOCK_DURATION
            from plugins.antiModule.spam import spam_log_aggregator
            guild_id = message.guild.id if message.guild else None
            spam_log_aggregator.add_spam_log(guild_id, message.author.id, "token", now)
            alert_type = "mass_token" if is_mass_token_spam else "token"
            return await TokenSpam.block_and_notify(
                message,
                message.author.id,
                now,
                alert_type,
                timeout_duration,
                "Token/Webhookスパム検知による自動タイムアウト",
            )
        return False
