from collections import deque
from plugins.antiModule.spam import (
    DEFAULT_TIMEOUT_DURATION,
    BaseSpam,
    _now,
)
from plugins.antiModule.bypass import MiniAntiBypass
import discord

# 転送スパム検知専用の時系列データ
user_forward_timestamps = {}


class ForwardSpam(BaseSpam):
    FORWARD_SPAM_COUNT = 5
    FORWARD_SPAM_WINDOW = 10
    log = False

    def __init__(self):
        self.forwarded_message_count = {}
        self.forward_threshold = 10

    def reset_forward_count(self, user_id):
        if user_id in self.forwarded_message_count:
            del self.forwarded_message_count[user_id]
        if user_id in user_forward_timestamps:
            del user_forward_timestamps[user_id]

    def handle_spam(self, user_id):
        print(f"User {user_id} is detected as spamming via message forwarding.")

    @staticmethod
    async def check_and_block_forward_spam(message: discord.Message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION):
        from plugins.antiModule.config import AntiCheatConfig
        log = ForwardSpam.log
        if log:
            print(f"[ForwardSpam][DEBUG] check_and_block_forward_spam called for user_id={getattr(message.author, 'id', None)}")
            print(f"[ForwardSpam][DEBUG] reference: {getattr(message, 'reference', None)}")
            print(f"[ForwardSpam][DEBUG] embeds: {getattr(message, 'embeds', None)}")
            print(f"[ForwardSpam][DEBUG] content: {getattr(message, 'content', None)}")
            print(f"[ForwardSpam][DEBUG] attachments: {getattr(message, 'attachments', None)}")
        if not await AntiCheatConfig.is_enabled(message.guild):
            if log:
                print("[ForwardSpam][DEBUG] AntiCheatConfig is not enabled for this guild.")
            return False
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "forward_spam"):
            if log:
                print("[ForwardSpam][DEBUG] forward_spam detection is not enabled.")
            return False
        if await MiniAntiBypass.should_bypass(message):
            if log:
                print("[ForwardSpam][DEBUG] User is bypassed.")
            return False
        uid = message.author.id
        now = _now()
        is_forwarded = False
        # 返信と転送の区別: referenceがあり、かつcontentが空、embedsが空でない場合などを転送とみなす
        if hasattr(message, "reference") and message.reference is not None:
            # Discordの返信は message.type == discord.MessageType.reply
            if getattr(message, "type", None) == getattr(discord.MessageType, "reply", None):
                is_forwarded = False
            else:
                is_forwarded = True
        elif any(getattr(e, "type", None) == "message_reference" for e in getattr(message, "embeds", [])):
            is_forwarded = True
        if log:
            print(f"[ForwardSpam][DEBUG] is_forwarded={is_forwarded}")
        if is_forwarded:
            if uid not in user_forward_timestamps:
                user_forward_timestamps[uid] = deque(maxlen=ForwardSpam.FORWARD_SPAM_COUNT * 2)
            user_forward_timestamps[uid].append(now)
            recent = [t for t in user_forward_timestamps[uid] if now - t < ForwardSpam.FORWARD_SPAM_WINDOW]
            if log:
                print(f"[ForwardSpam][DEBUG] recent_forward_count={len(recent)} times={recent}")
            if len(recent) >= ForwardSpam.FORWARD_SPAM_COUNT:
                from plugins.antiModule.spam import spam_log_aggregator
                guild_id = message.guild.id if message.guild else None
                spam_log_aggregator.add_spam_log(guild_id, uid, "forward", now)
                alert_type = "mass_forward" if guild_id and spam_log_aggregator.check_mass_spam(guild_id) else "forward"
                if log:
                    print(f"[ForwardSpam][DEBUG] SPAM DETECTED for user_id={uid} alert_type={alert_type}")
                return await ForwardSpam.block_and_notify(
                    message,
                    uid,
                    now,
                    alert_type,
                    timeout_duration,
                    "メッセージ転送スパム検知による自動タイムアウト",
                )
        return False


