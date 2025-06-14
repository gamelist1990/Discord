import difflib
import time
from collections import deque
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from .notifier import Notifier
from .bypass import MiniAntiBypass

# スパム検知用定数・グローバル変数
SIMILARITY_THRESHOLD = 0.85
RECENT_MSG_COUNT = 5
BLOCK_DURATION = 5 * 60  # デフォルト: 5分
DEFAULT_TIMEOUT_DURATION = 300  # Discordのタイムアウト
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

# 大人数スパム対応用の定数
MASS_SPAM_USER_THRESHOLD = 3  # 1分間に5人以上が検知されたら大人数スパムとみなす
MASS_SPAM_DETECTION_WINDOW = 10  # 検知ウィンドウ（秒）
MASS_SPAM_ENHANCED_SLOWMODE = 60  # 大人数スパム時のslowmode（1分）
MASS_SPAM_LOG_BUFFER_SIZE = 100  # ログバッファサイズ


def _now():
    return int(time.time())


class BaseSpam:
    """
    スパム検知・対処の基底クラス。
    共通のslowmode適用・解除、timeout、メッセージ削除、通知処理を集約。
    """
    _slowmode_apply_history = {}
    _slowmode_reset_tasks = {}
    _original_slowmode = {}
    _timeout_apply_history = {}
    _channel_history_cache = {}

    @staticmethod
    async def apply_slowmode(message, seconds, reason):
        """slowmodeを適用し、元の値を保存（既にslowmodeが設定されている場合も正確に記録）"""
        guild_id = message.guild.id
        channel_id = message.channel.id
        key = (guild_id, channel_id)
        try:
            # 既存のslowmode値を常に取得し記録
            orig_value = getattr(message.channel, "slowmode_delay", None)
            if orig_value is not None:
                # まだ記録されていない場合のみ保存
                if key not in BaseSpam._original_slowmode:
                    BaseSpam._original_slowmode[key] = orig_value
                # 既に記録済みだが値が変わっていれば最新値で上書き
                elif BaseSpam._original_slowmode[key] != orig_value:
                    BaseSpam._original_slowmode[key] = orig_value
        except Exception:
            pass
        await message.channel.edit(slowmode_delay=seconds, reason=reason)
        BaseSpam._slowmode_apply_history[key] = int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    async def reset_slowmode_if_no_spam(channel, author_id, guild_id, delay=60):
        """一定時間後に荒らしがなければslowmodeを元に戻す（必ず記録済み値に戻す）"""
        await asyncio.sleep(delay)
        now_aware = datetime.now(timezone.utc)
        recent_spam = False
        check_window = 60
        async for msg in channel.history(limit=50, oldest_first=False):
            if msg.guild and msg.guild.id == guild_id and msg.created_at:
                if (now_aware - msg.created_at).total_seconds() > check_window:
                    break
                if msg.author.id == author_id:
                    recent_spam = True
                    break
        if not recent_spam:
            try:
                key = (guild_id, channel.id)
                orig = BaseSpam._original_slowmode.get(key, 0)
                print(f"[INFO] Resetting slowmode to {orig}s for channel: {getattr(channel, 'id', None)} (guild: {guild_id}, no spam detected in last 1min)")
                await channel.edit(slowmode_delay=orig, reason="荒らし収束による自動slowmode解除")
            except Exception as e:
                print(f"[ERROR] Failed to reset slowmode: {e}")

    @staticmethod
    async def timeout_member(member, until, reason):
        try:
            if isinstance(member, discord.Member) and hasattr(member, "timeout"):
                await member.timeout(until, reason=reason)
                return True
        except Exception as e:
            print(f"[ERROR] Timeout failed: {e}")
        return False

    @staticmethod
    async def purge_user_messages(channel, user_id, window_sec=1800):
        """指定ユーザーの直近window_sec秒のメッセージを削除"""
        now_aware = datetime.now(timezone.utc)
        now_ts = now_aware.timestamp()
        messages = []
        async for msg in channel.history(limit=100, oldest_first=False):
            if msg.author.id == user_id and (now_ts - msg.created_at.timestamp()) <= window_sec:
                messages.append(msg)
        deleted_count = 0
        consecutive_429 = 0
        if len(messages) >= 2:
            try:
                await channel.delete_messages(messages)
                deleted_count = len(messages)
                print(f"[DEBUG] Bulk deleted {deleted_count} messages.")
            except discord.errors.HTTPException as e:
                if e.status == 429:
                    consecutive_429 += 1
                    print(f"[WARN] 429 detected on bulk delete, aborting and sleeping 30s.")
                    await asyncio.sleep(30)
                else:
                    print(f"[ERROR] HTTPException on bulk delete: {e}")
            except Exception as e:
                print(f"[ERROR] Bulk delete failed: {e}")
        else:
            for msg in messages:
                try:
                    await msg.delete()
                    deleted_count += 1
                    print(f"[DEBUG] Deleted message: {msg.id}")
                    await asyncio.sleep(5.0)
                except discord.errors.HTTPException as e:
                    if e.status == 429:
                        consecutive_429 += 1
                        print(f"[WARN] 429 detected, aborting further deletes and sleeping 30s.")
                        await asyncio.sleep(30)
                        break
                    else:
                        print(f"[ERROR] HTTPException deleting message {msg.id}: {e}")
                        break
                except Exception as e:
                    print(f"[ERROR] Failed to delete message {msg.id}: {e}")
                    break
                if consecutive_429 >= 2:
                    print("[WARN] Consecutive 429s, stopping delete loop.")
                    break
        print(f"[DEBUG] purge_user_messages (30min) complete. Deleted: {deleted_count}")
        return deleted_count

    @staticmethod
    async def handle_mass_spam_response(message, summary):
        """大人数スパム時の特別対応（slowmode適用後に一括処理）"""
        try:
            guild = message.guild
            if not guild:
                return

            print(f"[MASS SPAM] Handling mass spam response for guild {guild.id}")
            print(f"[MASS SPAM] Summary: {summary}")

            # 1. まず荒らされたチャンネルにslowmodeを適用し、完了までawait
            channel = message.channel
            slowmode_success = False
            if hasattr(channel, "edit"):
                try:
                    await channel.edit(
                        slowmode_delay=MASS_SPAM_ENHANCED_SLOWMODE,
                        reason="大人数スパム検知による緊急slowmode",
                    )
                    print(f"[MASS SPAM] Enhanced slowmode applied to {channel.id}")
                    slowmode_success = True
                except Exception as e:
                    print(
                        f"[MASS SPAM] Failed to apply enhanced slowmode to {channel.id}: {e}"
                    )
            if not slowmode_success:
                print(
                    "[MASS SPAM] Slowmode適用に失敗したため、以降の一括処理をスキップします。"
                )
                return

            # 2. slowmode適用後に一括で荒らしユーザーへkick/timeout/削除等を実施
            try:
                # 直近の荒らしユーザー一覧を取得
                user_ids = list(summary.get("user_counts", {}).keys())
                now_aware = datetime.now(timezone.utc)
                now_ts = now_aware.timestamp()
                for user_id in user_ids:
                    try:
                        member = await guild.fetch_member(int(user_id))
                        # タイムアウト（5分）
                        until = datetime.now(timezone.utc) + timedelta(
                            seconds=BLOCK_DURATION
                        )
                        await BaseSpam.timeout_member(member, until, "大人数スパム検知による自動タイムアウト")
                        print(f"[MASS SPAM] Timeout applied to user {user_id}")
                        # Kick（必要なら）
                        # await guild.kick(member, reason="大人数スパム検知による自動キック")
                        # print(f"[MASS SPAM] Kicked user {user_id}")
                        # メッセージ削除（アラート時刻から30分前まで）
                        deleted = await BaseSpam.purge_user_messages(channel, int(user_id), 1800)
                        print(
                            f"[MASS SPAM] Deleted {deleted} messages for user {user_id}"
                        )
                    except Exception as e:
                        print(f"[MASS SPAM] Failed to process user {user_id}: {e}")
            except Exception as e:
                print(f"[MASS SPAM] Error in mass spam batch processing: {e}")            # 管理者への緊急通知
            try:
                notifier = Notifier(message)
                # 大人数スパム時の通知：関与ユーザー数と削除メッセージ数を含める
                total_deleted = sum(summary.get("user_counts", {}).values())
                
                # 大人数スパム用の特別なalert_typeを送信
                await notifier.send_alert_notification("mass_spam", total_deleted)
                print(
                    f"[MASS SPAM] Mass spam alert sent: {summary['unique_users']} users involved, {total_deleted} messages processed"
                )
            except Exception as e:
                print(f"[MASS SPAM] Failed to send mass spam alert: {e}")

        except Exception as e:
            print(f"[MASS SPAM] Error in mass spam response: {e}")

    @staticmethod
    async def block_and_notify(message, uid, now, alert_type, timeout_duration, reason):
        import asyncio
        import discord
        from discord.utils import utcnow
        from datetime import timedelta, datetime, timezone

        print(
            f"[DEBUG] block_and_notify called: uid={uid}, alert_type={alert_type}, timeout_duration={timeout_duration}, reason={reason}"
        )

        # ログ集約システムにエントリを追加
        guild_id = message.guild.id if message.guild else None
        if guild_id:
            spam_log_aggregator.add_spam_log(guild_id, uid, alert_type, now)

            # 大人数スパムチェック
            if spam_log_aggregator.check_mass_spam(guild_id):
                if not spam_log_aggregator.is_mass_spam_active(guild_id):
                    spam_log_aggregator.activate_mass_spam_mode(guild_id)
                    summary = spam_log_aggregator.get_recent_spam_summary(guild_id)
                    await BaseSpam.handle_mass_spam_response(message, summary)

        user_blocked_until[uid] = now + BLOCK_DURATION
        # --- 荒らし検知時は真っ先にslowmodeを適用 ---
        slowmode_applied = False
        try:
            if (
                hasattr(message, "channel")
                and hasattr(message.channel, "edit")
                and hasattr(message, "guild")
                and message.guild is not None
            ):
                guild_id = message.guild.id
                channel_id = message.channel.id
                key = (guild_id, channel_id)
                now_ts = int(datetime.now(timezone.utc).timestamp())

                # 大人数スパム時は強化slowmodeを適用
                target_slowmode = (
                    MASS_SPAM_ENHANCED_SLOWMODE
                    if spam_log_aggregator.is_mass_spam_active(guild_id)
                    else 60
                )

                # --- slowmodeを設定 ---
                retry_count = 0
                while True:
                    try:
                        print(
                            f"[INFO] [PRIORITY] Setting slowmode to {target_slowmode}s for channel: {channel_id} (guild: {guild_id}) [retry {retry_count}]"
                        )
                        await message.channel.edit(
                            slowmode_delay=target_slowmode,
                            reason=(
                                "荒らし検知による自動低速モード"
                                if target_slowmode == 60
                                else "大人数スパム検知による緊急低速モード"
                            ),
                        )
                        BaseSpam._slowmode_apply_history[key] = int(
                            datetime.now(timezone.utc).timestamp()
                        )
                        slowmode_applied = True
                        break
                    except discord.errors.HTTPException as e:
                        if e.status == 429:
                            wait = getattr(e, "retry_after", None)
                            if wait is None:
                                wait = 5
                            print(
                                f"[WARN] 429 on slowmode, sleeping for {wait} seconds..."
                            )
                            await asyncio.sleep(wait)
                            retry_count += 1
                            continue
                        else:
                            print(
                                f"[ERROR] HTTPException (status={e.status}) slowmode: {e}"
                            )
                            break
                    except Exception as e:
                        print(f"[ERROR] Failed to set slowmode: {e}")
                        break
                # 既存のslowmode解除タスクがあればキャンセル
                task = BaseSpam._slowmode_reset_tasks.get(key)
                if task and not task.done():
                    task.cancel()

                # 大人数スパム時は長めの解除時間を設定
                reset_delay = 60  # 常に60秒で解除判定

                # 一定時間後に荒らしが収まっていればslowmodeを元の値に戻す
                task = asyncio.create_task(
                    BaseSpam.reset_slowmode_if_no_spam(
                        message.channel, message.author.id, guild_id, reset_delay
                    )
                )
                BaseSpam._slowmode_reset_tasks[key] = task
        except Exception as e:
            print(f"[ERROR] Failed to set slowmode: {e}")
        # --- timeout適用（簡潔化） ---
        member = None
        timeout_success = False
        timeout_skipped_for_403 = False
        until = utcnow() + timedelta(seconds=timeout_duration)
        try:
            if (
                hasattr(message, "guild")
                and message.guild is not None
                and hasattr(message, "author")
            ):
                guild_id = message.guild.id
                timeout_key = (guild_id, message.author.id)
                now_ts = int(datetime.now(timezone.utc).timestamp())
                last_timeout = BaseSpam._timeout_apply_history.get(timeout_key, 0)
                if now_ts - last_timeout > timeout_duration:
                    member = await message.guild.fetch_member(int(message.author.id))
                    timeout_success = await BaseSpam.timeout_member(member, until, reason)
                    if timeout_success:
                        BaseSpam._timeout_apply_history[timeout_key] = int(
                            datetime.now(timezone.utc).timestamp()
                        )
        except Exception as e:
            print(f"[DEBUG] fetch_member/timeout failed: {e}")
            member = message.author  # fallback
        if not timeout_success and not timeout_skipped_for_403:
            print(f"[ERROR] Timeout could not be applied for user: {uid}")
            return False        # --- メッセージ削除と通知処理（条件付きで実行） ---
        # slowmodeが適用され、かつtimeout_success時のみ削除処理を実行
        if slowmode_applied and timeout_success:

            async def safe_purge_user_messages():
                deleted_count = 0
                try:
                    channel = message.channel
                    now_aware = datetime.now(timezone.utc)
                    now_ts = now_aware.timestamp()
                    # アラート時刻(now)から30分前までのメッセージを全て削除対象に
                    messages = []
                    async for msg in channel.history(limit=100, oldest_first=False):
                        if (
                            msg.author.id == message.author.id
                            and (now_ts - msg.created_at.timestamp()) <= 1800
                        ):
                            messages.append(msg)
                    
                    consecutive_429 = 0
                    # --- 一括削除を優先 ---
                    if len(messages) >= 2:
                        try:
                            await channel.delete_messages(messages)
                            deleted_count = len(messages)
                            print(f"[DEBUG] Bulk deleted {deleted_count} messages.")
                        except discord.errors.HTTPException as e:
                            if e.status == 429:
                                consecutive_429 += 1
                                print(
                                    f"[WARN] 429 detected on bulk delete, aborting and sleeping 30s."
                                )
                                await asyncio.sleep(30)
                            else:
                                print(
                                    f"[ERROR] HTTPException on bulk delete: {e}"
                                )
                        except Exception as e:
                            print(f"[ERROR] Bulk delete failed: {e}")
                    else:
                        for msg in messages:
                            try:
                                await msg.delete()
                                deleted_count += 1
                                print(f"[DEBUG] Deleted message: {msg.id}")
                                await asyncio.sleep(5.0)
                            except discord.errors.HTTPException as e:
                                if e.status == 429:
                                    consecutive_429 += 1
                                    print(
                                        f"[WARN] 429 detected, aborting further deletes and sleeping 30s."
                                    )
                                    await asyncio.sleep(30)
                                    break
                                else:
                                    print(
                                        f"[ERROR] HTTPException deleting message {msg.id}: {e}"
                                    )
                                    break
                            except Exception as e:
                                print(f"[ERROR] Failed to delete message {msg.id}: {e}")
                                break
                            if consecutive_429 >= 2:
                                print("[WARN] Consecutive 429s, stopping delete loop.")
                                break
                    print(
                        f"[DEBUG] purge_user_messages (30min) complete. Deleted: {deleted_count}"
                    )
                    
                    # 個人スパム時の通知処理（大人数スパム時以外）
                    if not spam_log_aggregator.is_mass_spam_active(guild_id):
                        try:
                            notifier = Notifier(message)
                            await notifier.send_alert_notification(alert_type, deleted_count)
                            print(f"[DEBUG] Individual spam alert sent: type={alert_type}, deleted={deleted_count}")
                        except Exception as e:
                            print(f"[ERROR] Failed to send individual spam alert: {e}")
                            
                except Exception as e:
                    print(f"[ERROR] purge_user_messages failed: {e}")

            # バックグラウンドで削除処理
            asyncio.create_task(safe_purge_user_messages())
        else:
            print(
                "[INFO] メッセージ削除処理は、slowmode適用かつtimeout時のみ実行されます。条件を満たさないためスキップします。"
            )
        await asyncio.sleep(1.0)
        return True


class Spam(BaseSpam):
    @staticmethod
    async def check_and_block_spam(
        message: discord.Message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
        from .config import AntiCheatConfig

        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
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
            symbol_ratio = sum(1 for c in content if not c.isalnum()) / max(
                1, len(content)
            )
            if symbol_ratio > TEXT_SPAM_CONFIG["high_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["high_symbol_score"]
            elif symbol_ratio > TEXT_SPAM_CONFIG["medium_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["medium_symbol_score"]
        # 同一文字・数字の繰り返し判定
        import re
        repeated_char_match = re.search(r"(.)\1{7,}", content)
        repeated_digit_match = re.search(r"(\d)\1{7,}", content)
        uuid4_pattern = re.compile(
            r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}"
        )
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
            score += 0.3
        if len(content) > TEXT_SPAM_CONFIG["very_long_threshold"]:
            score += TEXT_SPAM_CONFIG["very_long_score"]
        elif len(content) > TEXT_SPAM_CONFIG["long_threshold"]:
            score += TEXT_SPAM_CONFIG["long_score"]
        elif len(content) <= TEXT_SPAM_CONFIG["very_short_threshold"]:
            score += TEXT_SPAM_CONFIG["very_short_score"]
        if re.search(r"[ぁ-んァ-ン一-龥]", content):
            score -= TEXT_SPAM_CONFIG["japanese_text_reduction"]
        if score >= TEXT_SPAM_CONFIG["base_threshold"]:
            # mass spam ログ追加・判定
            guild_id = message.guild.id if message.guild else None
            spam_log_aggregator.add_spam_log(guild_id, uid, "text", now)
            if guild_id and spam_log_aggregator.check_mass_spam(guild_id):
                alert_type = "mass_text"
            else:
                alert_type = "text"
            return await Spam.block_and_notify(
                message,
                uid,
                now,
                alert_type,
                timeout_duration,
                "テキストスパム検知による自動タイムアウト",
            )
        return False

class MediaSpam(BaseSpam):
    @staticmethod
    async def check_and_block_media_spam(
        message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
        from .config import AntiCheatConfig

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
        if message.attachments or any(
            e.type == "image" for e in getattr(message, "embeds", [])
        ):
            user_image_timestamps[uid].append(now)
            while (
                user_image_timestamps[uid]
                and now - user_image_timestamps[uid][0] > IMAGE_SPAM_WINDOW
            ):
                user_image_timestamps[uid].popleft()
            if len(user_image_timestamps[uid]) >= IMAGE_SPAM_THRESHOLD:
                # mass spam ログ追加・判定
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

class MentionSpam(BaseSpam):
    @staticmethod
    async def check_and_block_mention_spam(
        message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
        from .config import AntiCheatConfig

        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        if not await AntiCheatConfig.is_detection_enabled(
            message.guild, "mention_spam"
        ):
            return False
        if await MiniAntiBypass.should_bypass(message):
            return False
        uid = message.author.id
        now = _now()
        if uid not in user_mention_timestamps:
            user_mention_timestamps[uid] = deque()
        if message.mentions:
            user_mention_timestamps[uid].append(now)
            while (
                user_mention_timestamps[uid]
                and now - user_mention_timestamps[uid][0] > MENTION_SPAM_WINDOW
            ):
                user_mention_timestamps[uid].popleft()
            if len(user_mention_timestamps[uid]) >= MENTION_SPAM_THRESHOLD:
                # mass spam ログ追加・判定
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

class TokenSpam(BaseSpam):
    @staticmethod
    async def check_and_block_token_spam(
        message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
        from .config import AntiCheatConfig
        import re

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

        # UUID v4パターン検出（ブロック回避のためのuuid等も検知）
        uuid4_pattern = re.compile(
            r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}"
        )
        uuid4_matches = uuid4_pattern.findall(content)
        uuid4_count = len(uuid4_matches)
        # 類似度でグループ化
        matched_key = None
        for (gid, prev_content), entries in content_token_spam_map.items():
            if gid == message.guild.id:
                similarity = difflib.SequenceMatcher(
                    None, prev_content, content
                ).ratio()
                # uuid4を除外した上での類似性も判定
                prev_no_uuid = uuid4_pattern.sub("", prev_content)
                content_no_uuid = uuid4_pattern.sub("", content)
                similarity_no_uuid = difflib.SequenceMatcher(
                    None, prev_no_uuid, content_no_uuid
                ).ratio()
                if (
                    similarity >= TOKEN_SPAM_SIMILARITY_THRESHOLD
                    or similarity_no_uuid >= 0.8
                ):
                    matched_key = (gid, prev_content)
                    break
        if matched_key is None:
            matched_key = (message.guild.id, content)
            content_token_spam_map[matched_key] = deque()
        content_token_spam_map[matched_key].append((now, message.author.id))
        # 古い履歴を削除
        while (
            content_token_spam_map[matched_key]
            and now - content_token_spam_map[matched_key][0][0] > TOKEN_SPAM_WINDOW
        ):
            content_token_spam_map[matched_key].popleft()        # 3人以上が同一内容または高類似度内容を短時間で送信 or uuid4が2つ以上含まれる
        user_ids = set(uid for t, uid in content_token_spam_map[matched_key])
        is_mass_token_spam = len(user_ids) >= MASS_SPAM_USER_THRESHOLD
        
        if len(user_ids) >= TOKEN_SPAM_THRESHOLD or uuid4_count >= 2:
            for t, uid in content_token_spam_map[matched_key]:
                user_blocked_until[uid] = now + BLOCK_DURATION
            
            # 大人数Tokenスパムの場合はalert_typeを'mass_token'でblock_and_notifyを呼ぶ
            if is_mass_token_spam:
                # mass spam ログ追加・判定
                guild_id = message.guild.id if message.guild else None
                spam_log_aggregator.add_spam_log(guild_id, message.author.id, "token", now)
                await TokenSpam.block_and_notify(
                    message,
                    message.author.id,
                    now,
                    "mass_token",
                    timeout_duration,
                    "大人数Token/Webhookスパム検知による自動タイムアウト",
                )
            else:
                # 個人Tokenスパム時の処理
                guild_id = message.guild.id if message.guild else None
                spam_log_aggregator.add_spam_log(guild_id, message.author.id, "token", now)
                await TokenSpam.block_and_notify(
                    message,
                    message.author.id,
                    now,
                    "token",
                    timeout_duration,
                    "Token/Webhookスパム検知による自動タイムアウト",
                )
            return True
        return False


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
        from .config import AntiCheatConfig

        if not await AntiCheatConfig.is_enabled(message.guild):
            return False
        if not await AntiCheatConfig.is_detection_enabled(
            message.guild, "timebase_spam"
        ):
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
                    # mass spam ログ追加・判定
                    guild_id = message.guild.id if message.guild else None
                    spam_log_aggregator.add_spam_log(guild_id, uid, "timebase", now)
                    if guild_id and spam_log_aggregator.check_mass_spam(guild_id):
                        alert_type = "mass_timebase"
                    else:
                        alert_type = "timebase"
                    return await TimebaseSpam.block_and_notify(
                        message,
                        uid,
                        now,
                        alert_type,
                        timeout_duration,
                        "タイムベーススパム検知による自動タイムアウト",
                    )
        return False


class Block:
    @staticmethod
    async def is_user_blocked(message):
        uid = message.author.id
        now = _now()
        # ブロック中でもメッセージ自動削除は行わない
        if uid in user_blocked_until and user_blocked_until[uid] > now:
            return True
        return False

    @staticmethod
    async def handle_unblock(user_id, guild=None):
        # ブロック解除
        if user_id in user_blocked_until:
            del user_blocked_until[user_id]
        # タイムアウト解除（ギルドが指定されていれば解除を試みる）
        if guild is not None:
            try:
                member = await guild.fetch_member(int(user_id))
                if hasattr(member, "timeout"):
                    from discord.utils import utcnow

                    await member.timeout(
                        utcnow(),
                        reason="アンチチート解除コマンドによるタイムアウト解除",
                    )
            except Exception as e:
                print(f"[ERROR] Timeout解除失敗: {user_id} {e}")


class Griefing:
    @staticmethod
    async def handle_griefing(message, alert_type="text"):
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


class SpamLogAggregator:
    """スパム検知ログの集約と大人数スパム検知を行うクラス"""

    def __init__(self):
        self.log_buffer = deque(maxlen=MASS_SPAM_LOG_BUFFER_SIZE)
        self.guild_spam_counts = (
            {}
        )  # {guild_id: [(timestamp, user_id, alert_type), ...]}
        self.mass_spam_active = {}  # {guild_id: timestamp}
        self.processed_logs = set()  # 処理済みログのハッシュ

    def add_spam_log(self, guild_id, user_id, alert_type, timestamp=None):
        """スパム検知ログを追加"""
        if timestamp is None:
            timestamp = int(datetime.now(timezone.utc).timestamp())

        log_entry = {
            "guild_id": guild_id,
            "user_id": user_id,
            "alert_type": alert_type,
            "timestamp": timestamp,
        }

        # 重複チェック
        log_hash = f"{guild_id}_{user_id}_{alert_type}_{timestamp}"
        if log_hash in self.processed_logs:
            return False

        self.log_buffer.append(log_entry)
        self.processed_logs.add(log_hash)

        # ギルド別のカウント更新
        if guild_id not in self.guild_spam_counts:
            self.guild_spam_counts[guild_id] = deque()

        self.guild_spam_counts[guild_id].append((timestamp, user_id, alert_type))

        # 古いエントリを削除
        cutoff = timestamp - MASS_SPAM_DETECTION_WINDOW
        while (
            self.guild_spam_counts[guild_id]
            and self.guild_spam_counts[guild_id][0][0] < cutoff
        ):
            self.guild_spam_counts[guild_id].popleft()

        return True

    def check_mass_spam(self, guild_id):
        """大人数スパムかどうかチェック"""
        if guild_id not in self.guild_spam_counts:
            return False

        recent_logs = self.guild_spam_counts[guild_id]
        if len(recent_logs) < MASS_SPAM_USER_THRESHOLD:
            return False

        # 異なるユーザー数をカウント
        unique_users = set(user_id for _, user_id, _ in recent_logs)

        return len(unique_users) >= MASS_SPAM_USER_THRESHOLD

    def get_recent_spam_summary(self, guild_id, window_seconds=60):
        """最近のスパム検知サマリーを取得"""
        if guild_id not in self.guild_spam_counts:
            return {}

        now = int(datetime.now(timezone.utc).timestamp())
        cutoff = now - window_seconds

        recent_logs = [
            log for log in self.guild_spam_counts[guild_id] if log[0] >= cutoff
        ]

        summary = {
            "total_detections": len(recent_logs),
            "unique_users": len(set(user_id for _, user_id, _ in recent_logs)),
            "alert_types": {},
            "user_counts": {},
        }

        for _, user_id, alert_type in recent_logs:
            summary["alert_types"][alert_type] = (
                summary["alert_types"].get(alert_type, 0) + 1
            )
            summary["user_counts"][user_id] = summary["user_counts"].get(user_id, 0) + 1

        return summary

    def is_mass_spam_active(self, guild_id):
        """大人数スパムが進行中かチェック"""
        if guild_id not in self.mass_spam_active:
            return False

        # 10分間は大人数スパム状態を維持
        cutoff = int(datetime.now(timezone.utc).timestamp()) - 600
        return self.mass_spam_active[guild_id] > cutoff

    def activate_mass_spam_mode(self, guild_id):
        """大人数スパムモードを有効化"""
        self.mass_spam_active[guild_id] = int(datetime.now(timezone.utc).timestamp())
        print(f"[MASS SPAM] Mass spam mode activated for guild {guild_id}")


class SpamStatistics:
    """スパム統計とレポート機能"""

    @staticmethod
    def get_spam_statistics(guild_id, time_range_minutes=60):
        """指定された時間範囲のスパム統計を取得"""
        summary = spam_log_aggregator.get_recent_spam_summary(
            guild_id, time_range_minutes * 60
        )

        # より詳細な統計情報を追加
        statistics = {
            "period_minutes": time_range_minutes,
            "total_detections": summary["total_detections"],
            "unique_users": summary["unique_users"],
            "detection_rate": (
                summary["total_detections"] / time_range_minutes
                if time_range_minutes > 0
                else 0
            ),
            "alert_breakdown": summary["alert_types"],
            "top_spammers": sorted(
                summary["user_counts"].items(), key=lambda x: x[1], reverse=True
            )[:10],
            "is_mass_spam_active": spam_log_aggregator.is_mass_spam_active(guild_id),
            "timestamp": int(datetime.now(timezone.utc).timestamp()),
        }

        return statistics

    @staticmethod
    def format_spam_report(guild_id, time_range_minutes=60):
        """スパムレポートを文字列として整形"""
        stats = SpamStatistics.get_spam_statistics(guild_id, time_range_minutes)

        report = f"📊 **スパム検知レポート** (過去{time_range_minutes}分)\n"
        report += f"• 検知総数: {stats['total_detections']}件\n"
        report += f"• 関与ユーザー数: {stats['unique_users']}人\n"
        report += f"• 検知レート: {stats['detection_rate']:.2f}件/分\n"

        if stats["is_mass_spam_active"]:
            report += f"🚨 **大人数スパム警報発令中**\n"

        if stats["alert_breakdown"]:
            report += f"\n**検知タイプ別:**\n"
            for alert_type, count in stats["alert_breakdown"].items():
                report += f"• {alert_type}: {count}件\n"

        if stats["top_spammers"]:
            report += f"\n**上位スパマー:**\n"
            for i, (user_id, count) in enumerate(stats["top_spammers"][:5]):
                report += f"{i+1}. <@{user_id}>: {count}件\n"

        return report


# グローバルなログ集約インスタンス
spam_log_aggregator = SpamLogAggregator()
