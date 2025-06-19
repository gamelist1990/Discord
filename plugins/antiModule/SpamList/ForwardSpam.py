from plugins.antiModule.spam import (
    DEFAULT_TIMEOUT_DURATION,
    BaseSpam,
    _now,
    user_recent_messages,
)
from plugins.antiModule.bypass import MiniAntiBypass
import discord
from collections import deque


class ForwardSpam(BaseSpam):
    FORWARD_SPAM_COUNT = 5
    FORWARD_SPAM_WINDOW = 30

    def __init__(self):
        self.forwarded_message_count = {}
        self.forward_threshold = 10

    def check_forward_spam(self, user_id, message):
        if message.get("is_forwarded", False):
            self.forwarded_message_count[user_id] = self.forwarded_message_count.get(user_id, 0) + 1
            if self.forwarded_message_count[user_id] > self.forward_threshold:
                return True
        return False

    def reset_forward_count(self, user_id):
        if user_id in self.forwarded_message_count:
            del self.forwarded_message_count[user_id]

    def handle_spam(self, user_id):
        print(f"User {user_id} is detected as spamming via message forwarding.")

    @staticmethod
    async def check_and_block_forward_spam(message: discord.Message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        from plugins.antiModule.config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "forward_spam"):
            return False
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        is_forwarded = False
        if getattr(message, "reference", None) is not None:
            is_forwarded = True
        elif any(getattr(e, "type", None) == "message_reference" for e in getattr(message, "embeds", [])):
            is_forwarded = True
        if uid not in user_recent_messages:
            user_recent_messages[uid] = deque(maxlen=10)
        if is_forwarded:
            user_recent_messages[uid].append(now)
            recent = [t for t in user_recent_messages[uid] if now - t < 30]
            if len(recent) >= 5:
                from plugins.antiModule.spam import spam_log_aggregator
                guild_id = message.guild.id if message.guild else None
                spam_log_aggregator.add_spam_log(guild_id, uid, "forward", now)
                alert_type = "mass_forward" if guild_id and spam_log_aggregator.check_mass_spam(guild_id) else "forward"
                return await ForwardSpam.block_and_notify(
                    message,
                    uid,
                    now,
                    alert_type,
                    timeout_duration,
                    "メッセージ転送スパム検知による自動タイムアウト",
                )
        return False


if __name__ == "__main__":
    spam_detector = ForwardSpam()

    messages = [
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
        {"user_id": "user1", "is_forwarded": True},
    ]

    for msg in messages:
        user_id = msg["user_id"]
        if spam_detector.check_forward_spam(user_id, msg):
            spam_detector.handle_spam(user_id)
            spam_detector.reset_forward_count(user_id)
