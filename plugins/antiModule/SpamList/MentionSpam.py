from plugins.antiModule.spam import (
    MENTION_SPAM_THRESHOLD,
    MENTION_SPAM_WINDOW,
    user_mention_timestamps as _user_mention_timestamps,
    DEFAULT_TIMEOUT_DURATION,
    _now,
)
from plugins.antiModule.bypass import MiniAntiBypass
from collections import deque
import discord
from plugins.antiModule.spam import BaseSpam

user_mention_history = {}


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
        # 直近2回分のメンション履歴を記録
        if uid not in user_mention_history:
            user_mention_history[uid] = deque(maxlen=2)
        mention_ids = [m.id for m in getattr(message, 'mentions', []) if isinstance(m, discord.User) or isinstance(m, discord.Member)]
        role_mention_ids = [r.id for r in getattr(message, 'role_mentions', [])]
        mention_everyone = getattr(message, 'mention_everyone', False)
        user_mention_history[uid].append({
            'time': now,
            'mention_ids': mention_ids,
            'role_mention_ids': role_mention_ids,
            'mention_everyone': mention_everyone
        })
        # 既存のウィンドウ方式も記録
        if message.mentions or message.role_mentions or mention_everyone:
            if uid not in _user_mention_timestamps:
                _user_mention_timestamps[uid] = deque()
            _user_mention_timestamps[uid].append(now)
            while _user_mention_timestamps[uid] and now - _user_mention_timestamps[uid][0] > MENTION_SPAM_WINDOW:
                _user_mention_timestamps[uid].popleft()
        # スコアリング
        score = 0
        # 直近2回の履歴でスパムパターン
        if len(user_mention_history[uid]) == 2:
            h1, h2 = user_mention_history[uid][0], user_mention_history[uid][1]
            # 個人2人メンション連続
            if len(h1['mention_ids']) == 2 and len(h2['mention_ids']) == 2:
                score += 1
            # ロールメンション連続
            if len(h1['role_mention_ids']) > 0 and len(h2['role_mention_ids']) > 0:
                score += 1
            # @everyone/@here連続
            if h1['mention_everyone'] and h2['mention_everyone']:
                score += 1
        # ウィンドウ内のメンション回数
        if uid in _user_mention_timestamps and len(_user_mention_timestamps[uid]) >= MENTION_SPAM_THRESHOLD:
            score += 1
        # 閾値（例: 2）
        if score >= 2:
            from plugins.antiModule.spam import spam_log_aggregator
            guild_id = message.guild.id if message.guild else None
            spam_log_aggregator.add_spam_log(guild_id, uid, "mention", now)
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
