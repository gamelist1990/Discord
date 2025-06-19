from plugins.antiModule.spam import IMAGE_SPAM_THRESHOLD, IMAGE_SPAM_WINDOW, user_image_timestamps, DEFAULT_TIMEOUT_DURATION, _now
from plugins.antiModule.bypass import MiniAntiBypass
from collections import deque
import discord
from plugins.antiModule.spam import BaseSpam

class MediaSpam(BaseSpam):
    @staticmethod
    async def check_and_block_media_spam(message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        from plugins.antiModule.config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "image_spam"):
            return False
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        if uid not in user_image_timestamps:
            user_image_timestamps[uid] = deque()
        if message.attachments or any(e.type == "image" for e in getattr(message, "embeds", [])):
            user_image_timestamps[uid].append(now)
            while user_image_timestamps[uid] and now - user_image_timestamps[uid][0] > IMAGE_SPAM_WINDOW:
                user_image_timestamps[uid].popleft()
            if len(user_image_timestamps[uid]) >= IMAGE_SPAM_THRESHOLD:
                from plugins.antiModule.spam import spam_log_aggregator
                guild_id = message.guild.id if message.guild else None
                spam_log_aggregator.add_spam_log(guild_id, uid, "image", now)
                if guild_id and spam_log_aggregator.check_mass_spam(guild_id):
                    alert_type = "mass_image"
                else:
                    alert_type = "image"
                return await MediaSpam.block_and_notify(
                    message,
                    uid,
                    now,
                    alert_type,
                    timeout_duration,
                    "画像・動画スパム検知による自動タイムアウト",
                )
        return False
