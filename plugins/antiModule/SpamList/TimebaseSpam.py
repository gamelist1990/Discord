from plugins.antiModule.spam import user_time_intervals, DEFAULT_TIMEOUT_DURATION, _now
from plugins.antiModule.bypass import MiniAntiBypass
from collections import deque
import discord
from plugins.antiModule.spam import BaseSpam

class TimebaseSpam(BaseSpam):
    @staticmethod
    async def check_and_block_timebase_spam(
        message,
        min_msgs=8,
        var_threshold=0.15,
        hist_threshold=0.7,
        max_history=15,
        reset_interval=60,
        similarity_threshold=0.85,
        timeout_duration: int = DEFAULT_TIMEOUT_DURATION,
    ):
        from plugins.antiModule.config import AntiCheatConfig
        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        if not await AntiCheatConfig.is_detection_enabled(message.guild, "timebase_spam"):
            return False
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        if uid not in user_time_intervals:
            user_time_intervals[uid] = deque(maxlen=max_history)
        if hasattr(message, "created_at"):
            ts = int(message.created_at.timestamp())
        else:
            ts = now
        if user_time_intervals[uid]:
            interval = ts - user_time_intervals[uid][-1][0]
            user_time_intervals[uid].append((ts, interval))
        else:
            user_time_intervals[uid].append((ts, 0))
        if len(user_time_intervals[uid]) >= min_msgs:
            intervals = [iv for t, iv in list(user_time_intervals[uid])[1:]]
            if intervals:
                mean = sum(intervals) / len(intervals)
                var = sum((iv - mean) ** 2 for iv in intervals) / len(intervals)
                if var < var_threshold:
                    from plugins.antiModule.spam import spam_log_aggregator
                    guild_id = message.guild.id if message.guild else None
                    spam_log_aggregator.add_spam_log(guild_id, uid, "timebase", now)
                    alert_type = "mass_timebase" if guild_id and spam_log_aggregator.check_mass_spam(guild_id) else "timebase"
                    return await TimebaseSpam.block_and_notify(
                        message,
                        uid,
                        now,
                        alert_type,
                        timeout_duration,
                        "タイムベーススパム検知による自動タイムアウト",
                    )
        return False
