from plugins.antiModule.spam import (
    MENTION_SPAM_THRESHOLD,
    MENTION_SPAM_WINDOW,
    user_mention_timestamps,
    DEFAULT_TIMEOUT_DURATION,
    _now,
)
from plugins.antiModule.bypass import MiniAntiBypass
from collections import deque
import discord
from plugins.antiModule.spam import BaseSpam


class MentionSpam(BaseSpam):
    @staticmethod
    async def check_and_block_mention_spam(
        message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
        from plugins.antiModule.config import AntiCheatConfig

        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
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
                from plugins.antiModule.spam import spam_log_aggregator

                guild_id = message.guild.id if message.guild else None
                spam_log_aggregator.add_spam_log(guild_id, uid, "mention", now)
                if guild_id and spam_log_aggregator.check_mass_spam(guild_id):
                    alert_type = "mass_mention"
                else:
                    alert_type = "mention"
                return await MentionSpam.block_and_notify(
                    message,
                    uid,
                    now,
                    alert_type,
                    timeout_duration,
                    "メンションスパム検知による自動タイムアウト",
                )
        return False
