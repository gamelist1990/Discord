import difflib
import time
from collections import deque

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


def _now():
    return int(time.time())


class BaseSpam:
    @staticmethod
    async def block_and_notify(message, uid, now, alert_type, timeout_duration, reason):
        import asyncio
        import discord
        from discord.utils import utcnow
        from datetime import timedelta, datetime, timezone

        print(
            f"[DEBUG] block_and_notify called: uid={uid}, alert_type={alert_type}, timeout_duration={timeout_duration}, reason={reason}"
        )
        user_blocked_until[uid] = now + BLOCK_DURATION
        # --- キャッシュ履歴dictの初期化 ---
        if not hasattr(BaseSpam, "_slowmode_apply_history"):
            BaseSpam._slowmode_apply_history = (
                {}
            )  # key=(guild_id, channel_id): timestamp
        if not hasattr(BaseSpam, "_timeout_apply_history"):
            BaseSpam._timeout_apply_history = {}  # key=(guild_id, user_id): timestamp
        if not hasattr(BaseSpam, "_alert_history"):
            BaseSpam._alert_history = (
                {}
            )  # key=(guild_id, channel_id, user_id, alert_type): [timestamps]
        if not hasattr(BaseSpam, "_delete_history"):
            BaseSpam._delete_history = (
                {}
            )  # key=(guild_id, channel_id, user_id): timestamp
        # --- チャンネル履歴キャッシュ ---
        if not hasattr(BaseSpam, "_channel_history_cache"):
            BaseSpam._channel_history_cache = {}  # key=(guild_id, channel_id): (timestamp, [messages])
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
                last_slowmode = BaseSpam._slowmode_apply_history.get(key, 0)
                if now_ts - last_slowmode > 60:
                    retry_count = 0
                    while True:
                        try:
                            print(
                                f"[INFO] [PRIORITY] Setting slowmode to 60s for channel: {channel_id} (guild: {guild_id}) [retry {retry_count}]"
                            )
                            await message.channel.edit(
                                slowmode_delay=60,
                                reason="荒らし検知による自動低速モード",
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
                if not hasattr(BaseSpam, "_slowmode_reset_tasks"):
                    BaseSpam._slowmode_reset_tasks = {}
                task = BaseSpam._slowmode_reset_tasks.get(key)
                if task and not task.done():
                    task.cancel()

                # 1分後に荒らしが収まっていればslowmodeを解除
                async def reset_slowmode_if_no_spam(channel, author_id, guild_id):
                    await asyncio.sleep(60)
                    now_aware = datetime.now(timezone.utc)
                    recent_count = 0
                    async for msg in channel.history(limit=30, oldest_first=False):
                        if (
                            msg.guild
                            and msg.guild.id == guild_id
                            and msg.author.id == author_id
                            and msg.created_at
                            and (now_aware - msg.created_at).total_seconds() <= 60
                        ):
                            recent_count += 1
                    if recent_count <= 1:
                        try:
                            print(
                                f"[INFO] Resetting slowmode to 0s for channel: {getattr(channel, 'id', None)} (guild: {guild_id}, no spam detected)"
                            )
                            await channel.edit(
                                slowmode_delay=1,
                                reason="荒らし収束による自動slowmode解除",
                            )
                        except Exception as e:
                            print(f"[ERROR] Failed to reset slowmode: {e}")

                task = asyncio.create_task(
                    reset_slowmode_if_no_spam(
                        message.channel, message.author.id, guild_id
                    )
                )
                BaseSpam._slowmode_reset_tasks[key] = task
        except Exception as e:
            print(f"[ERROR] Failed to set slowmode: {e}")
        # --- timeout適用（429時は成功までリトライ、履歴は成功時のみ更新） ---
        member = None
        timeout_success = False
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
                    print(
                        f"[DEBUG] fetching member: guild_id={getattr(message.guild, 'id', None)}, author_id={getattr(message.author, 'id', None)}"
                    )
                    member = await message.guild.fetch_member(int(message.author.id))
                    for m in [member, message.author]:
                        retry_count = 0
                        while True:
                            try:
                                print(
                                    f"[DEBUG] Trying timeout for: {getattr(m,  'id', None)} (retry {retry_count})"
                                )
                                if isinstance(m, discord.Member) and hasattr(
                                    m, "timeout"
                                ):
                                    await m.timeout(until, reason=reason)
                                    print(
                                        f"[DEBUG] Timeout success for: {getattr(m, 'id', None)}"
                                    )
                                    timeout_success = True
                                    BaseSpam._timeout_apply_history[timeout_key] = int(
                                        datetime.now(timezone.utc).timestamp()
                                    )
                                    break
                            except discord.errors.HTTPException as e:
                                if e.status == 429:
                                    wait = getattr(e, "retry_after", None)
                                    if wait is None:
                                        wait = 5
                                    print(
                                        f"[WARN] 429 on timeout, sleeping for {wait} seconds..."
                                    )
                                    await asyncio.sleep(wait)
                                    retry_count += 1
                                    continue
                                else:
                                    print(
                                        f"[ERROR] HTTPException (status={e.status}) timeout: {e}"
                                    )
                                    break
                            except Exception as e:
                                print(
                                    f"[DEBUG] Timeout failed for {getattr(m, 'id', None)}: {e}"
                                )
                                await asyncio.sleep(2)
                                retry_count += 1
                                continue
                            else:
                                break
                        if timeout_success:
                            break
                else:
                    print(
                        f"[DEBUG] Timeout already applied recently for {timeout_key}, skipping."
                    )
                    timeout_success = True
        except Exception as e:
            print(f"[DEBUG] fetch_member/timeout failed: {e}")
            member = message.author  # fallback
        if not timeout_success:
            print(f"[ERROR] Timeout could not be applied for user: {uid}")
            return False
        # --- メッセージ削除（429時は成功までリトライ、履歴は成功時のみ更新、並行処理制限） ---
        try:
            # --- 継続的なスパムならkick（従来通り） ---
            try:
                # 直近1分間で5回以上block_and_notifyが呼ばれていたらkick
                if (
                    hasattr(message, "guild")
                    and message.guild is not None
                    and hasattr(message, "author")
                ):
                    from datetime import datetime, timezone

                    if not hasattr(BaseSpam, "_block_history"):
                        BaseSpam._block_history = {}
                    now_ts = int(datetime.now(timezone.utc).timestamp())
                    key = (message.guild.id, message.author.id)
                    if key not in BaseSpam._block_history:
                        BaseSpam._block_history[key] = []
                    BaseSpam._block_history[key].append(now_ts)
                    # 1分以内の履歴だけ残す
                    BaseSpam._block_history[key] = [
                        t for t in BaseSpam._block_history[key] if now_ts - t <= 60
                    ]
                    if len(BaseSpam._block_history[key]) >= 5:
                        try:
                            print(
                                f"[WARN] User {message.author.id} is persistently spamming. Kicking..."
                            )
                            await message.guild.kick(
                                message.author,
                                reason="継続的なスパム検知による自動キック",
                            )
                            print(
                                f"[INFO] User {message.author.id} kicked for persistent spam."
                            )
                            # kick後は履歴クリア
                            BaseSpam._block_history[key] = []
                        except Exception as e:
                            print(
                                f"[ERROR] Failed to kick user {message.author.id}: {e}"
                            )
            except Exception as e:
                print(f"[ERROR] kick判定処理失敗: {e}")

            # --- Alert処理 ---
            try:
                if not hasattr(BaseSpam, "_alert_history"):
                    BaseSpam._alert_history = {}
                alert_key = (
                    (
                        message.guild.id
                        if hasattr(message, "guild") and message.guild
                        else None
                    ),
                    message.channel.id if hasattr(message, "channel") else None,
                    message.author.id,
                    alert_type,
                )
                now_aware = datetime.now(timezone.utc)
                now_ts = int(now_aware.timestamp())
                # alert履歴確認
                history = BaseSpam._alert_history.get(alert_key, [])
                history = [t for t in history if now_ts - t <= 30]
                if history:
                    print(
                        f"[DEBUG] Alert already sent recently for {alert_key}, skipping duplicate alert."
                    )
                else:
                    from .notifier import Notifier

                    await Notifier(message).send_alert_notification(alert_type, 0)
                    print(f"[DEBUG] Alert notification sent for {alert_type}")
                history.append(now_ts)
                BaseSpam._alert_history[alert_key] = history
            except Exception as e:
                print(f"[ERROR] Alert notification failed: {e}")

            # --- メッセージ削除処理（Alert処理の後に実行） ---
            try:
                if not hasattr(BaseSpam, "_delete_history"):
                    BaseSpam._delete_history = {}
                if not hasattr(BaseSpam, "_delete_semaphore"):
                    BaseSpam._delete_semaphore = asyncio.Semaphore(
                        1
                    )  # 同時削除処理を1つに制限
                delete_key = (
                    (
                        message.guild.id
                        if hasattr(message, "guild") and message.guild
                        else None
                    ),
                    message.channel.id if hasattr(message, "channel") else None,
                    message.author.id,
                )
                now_aware = datetime.now(timezone.utc)
                now_ts = int(now_aware.timestamp())
                last_delete = BaseSpam._delete_history.get(delete_key, 0)
                deleted_count = 0
                if now_ts - last_delete > 30:
                    async with BaseSpam._delete_semaphore:
                        dummy_msg = message
                        dummy_msg.author = (
                            member if member is not None else message.author
                        )
                        dummy_msg.guild = message.guild
                        dummy_msg.channel = message.channel
                        channel = dummy_msg.channel
                        MAX_DELETE_PER_BLOCK = 15
                        # --- チャンネル履歴キャッシュ利用 ---
                        # guild_idの取得を安全に
                        if getattr(channel, "guild", None) and getattr(channel.guild, "id", None):
                            guild_id = channel.guild.id
                        elif getattr(message, "guild", None) and getattr(message.guild, "id", None):
                            guild_id = message.guild.id
                        else:
                            guild_id = None
                        cache_key = (guild_id, channel.id)
                        cache = BaseSpam._channel_history_cache.get(cache_key, None)
                        if cache:
                            cache_time, cache_msgs = cache
                            if (now_aware - cache_time).total_seconds() < 10:
                                messages = cache_msgs
                            else:
                                messages = []
                        else:
                            messages = []
                        if not messages:
                            retry_count_history = 0
                            while retry_count_history < 3:
                                try:
                                    messages = [msg async for msg in channel.history(limit=50, oldest_first=False)]
                                    BaseSpam._channel_history_cache[cache_key] = (now_aware, messages)
                                    break
                                except discord.errors.HTTPException as e:
                                    if e.status == 429:
                                        wait = getattr(e, "retry_after", None) or 5
                                        print(
                                            f"[WARN] 429 on history fetch, sleeping for {wait} seconds..."
                                        )
                                        await asyncio.sleep(wait)
                                        retry_count_history += 1
                                        continue
                                    else:
                                        print(f"[ERROR] HTTPException on history: {e}")
                                        break
                                except Exception as e:
                                    print(f"[ERROR] Failed to fetch history: {e}")
                                    break
                        # 削除対象メッセージ抽出（キャッシュ利用）
                        messages_to_delete = []
                        for msg in messages:
                            if msg.channel.id != channel.id:
                                continue
                            if msg.author.id == dummy_msg.author.id:
                                if (
                                    msg.created_at
                                    and (now_aware - msg.created_at).total_seconds() <= 1800
                                ):
                                    messages_to_delete.append(msg)
                                    if len(messages_to_delete) >= MAX_DELETE_PER_BLOCK:
                                        break
                                elif (
                                    msg.created_at
                                    and (now_aware - msg.created_at).total_seconds() > 1800
                                ):
                                    break
                        # 一括削除（bulk_delete）は2件以上かつ全てが14日以内のメッセージのみ可能
                        if len(messages_to_delete) >= 2:
                            # 10件ずつ分割してbulk_delete
                            for i in range(0, len(messages_to_delete), 10):
                                chunk = messages_to_delete[i:i+10]
                                try:
                                    await channel.delete_messages(chunk)
                                    deleted_count += len(chunk)
                                    print(f"[DEBUG] Bulk deleted {len(chunk)} messages.")
                                except Exception as e:
                                    print(
                                        f"[WARN] Bulk delete failed, fallback to individual delete: {e}"
                                    )
                                    for msg in chunk:
                                        retry_count = 0
                                        while retry_count < 5:
                                            try:
                                                await msg.delete()
                                                deleted_count += 1
                                                print(f"[DEBUG] Deleted message: {msg.id}")
                                                await asyncio.sleep(2.5)
                                                break
                                            except discord.errors.HTTPException as e:
                                                if e.status == 429:
                                                    wait = (
                                                        getattr(e, "retry_after", None) or 8
                                                    )
                                                    print(
                                                        f"[WARN] 429 detected, sleeping for {wait} seconds..."
                                                    )
                                                    await asyncio.sleep(wait)
                                                    retry_count += 1
                                                    continue
                                                else:
                                                    print(
                                                        f"[ERROR] HTTPException (status={e.status}) deleting message {msg.id}: {e}"
                                                    )
                                                    break
                                            except Exception as e:
                                                print(
                                                    f"[ERROR] Failed to delete message {msg.id}: {e}"
                                                )
                                                break
                        else:
                            for msg in messages_to_delete:
                                retry_count = 0
                                while retry_count < 5:
                                    try:
                                        await msg.delete()
                                        deleted_count += 1
                                        print(f"[DEBUG] Deleted message: {msg.id}")
                                        await asyncio.sleep(2.5)
                                        break
                                    except discord.errors.HTTPException as e:
                                        if e.status == 429:
                                            wait = getattr(e, "retry_after", None) or 8
                                            print(
                                                f"[WARN] 429 detected, sleeping for {wait} seconds..."
                                            )
                                            await asyncio.sleep(wait)
                                            retry_count += 1
                                            continue
                                        else:
                                            print(
                                                f"[ERROR] HTTPException (status={e.status}) deleting message {msg.id}: {e}"
                                            )
                                            break
                                    except Exception as e:
                                        print(
                                            f"[ERROR] Failed to delete message {msg.id}: {e}"
                                        )
                                        break
                    BaseSpam._delete_history[delete_key] = int(
                        datetime.now(timezone.utc).timestamp()
                    )
                    print(
                        f"[DEBUG] purge_user_messages (30min, max 15) complete. Deleted: {deleted_count}"
                    )
                else:
                    print(
                        f"[DEBUG] Message deletion already done recently for {delete_key}, skipping."
                    )
                    deleted_count = 0
            except Exception as e:
                print(f"[ERROR] purge_user_messages failed: {e}")
        except Exception as e:
            print(f"[ERROR] block_and_notify main try failed: {e}")
        await asyncio.sleep(1.0)
        return True


class Spam(BaseSpam):
    @staticmethod
    async def check_and_block_spam(
        message: discord.Message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
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
            symbol_ratio = sum(1 for c in content if not c.isalnum()) / max(
                1, len(content)
            )
            if symbol_ratio > TEXT_SPAM_CONFIG["high_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["high_symbol_score"]
            elif symbol_ratio > TEXT_SPAM_CONFIG["medium_symbol_threshold"]:
                score += TEXT_SPAM_CONFIG["medium_symbol_score"]
        # 同一文字・数字の繰り返し判定
        # 8文字以上の連続した同一文字や数字があればスコア加算
        import re

        repeated_char_match = re.search(r"(.)\1{7,}", content)
        repeated_digit_match = re.search(r"(\d)\1{7,}", content)
        # UUID v4パターン検出（text spamでも検知）
        uuid4_pattern = re.compile(
            r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-4[a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}"
        )
        uuid4_matches = uuid4_pattern.findall(content)
        uuid4_count = len(uuid4_matches)
        # ドット区切りの短文パターン（a.a.a.a.a._. など）
        dot_pattern = re.compile(r"(?:[a-zA-Z0-9]\.){4,}[a-zA-Z0-9_]+")
        dot_matches = dot_pattern.findall(content)
        dot_count = len(dot_matches)
        if repeated_char_match or repeated_digit_match:
            score += 0.4  # 必要に応じてスコア調整
        if uuid4_count >= 2:
            score += 0.5  # UUID4が2つ以上含まれる場合は強くスコア加算
        elif uuid4_count == 1:
            score += 0.25  # 1つでも加算
        if dot_count >= 1:
            score += 0.3  # ドット区切り短文が含まれる場合も加算
        # 長文・短文
        if len(content) > TEXT_SPAM_CONFIG["very_long_threshold"]:
            score += TEXT_SPAM_CONFIG["very_long_score"]
        elif len(content) > TEXT_SPAM_CONFIG["long_threshold"]:
            score += TEXT_SPAM_CONFIG["long_score"]
        elif len(content) <= TEXT_SPAM_CONFIG["very_short_threshold"]:
            score += TEXT_SPAM_CONFIG["very_short_score"]
        # 日本語テキスト判定
        if re.search(r"[ぁ-んァ-ン一-龥]", content):
            score -= TEXT_SPAM_CONFIG["japanese_text_reduction"]
        # スコア判定
        if score >= TEXT_SPAM_CONFIG["base_threshold"]:
            return await Spam.block_and_notify(
                message,
                uid,
                now,
                "text",
                timeout_duration,
                "テキストスパム検知による自動タイムアウト",
            )
        return False


class MediaSpam(BaseSpam):
    @staticmethod
    async def check_and_block_media_spam(
        message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
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
        if message.attachments or any(
            e.type == "image" for e in getattr(message, "embeds", [])
        ):
            user_image_timestamps[uid].append(now)
            # 古い履歴を削除
            while (
                user_image_timestamps[uid]
                and now - user_image_timestamps[uid][0] > IMAGE_SPAM_WINDOW
            ):
                user_image_timestamps[uid].popleft()
            if len(user_image_timestamps[uid]) >= IMAGE_SPAM_THRESHOLD:
                return await MediaSpam.block_and_notify(
                    message,
                    uid,
                    now,
                    "image",
                    timeout_duration,
                    "画像・動画スパム検知による自動タイムアウト",
                )
        return False


class MentionSpam(BaseSpam):
    @staticmethod
    async def check_and_block_mention_spam(
        message, timeout_duration: int = DEFAULT_TIMEOUT_DURATION
    ):
        # AntiCheat全体が無効な場合は処理しない
        from .config import AntiCheatConfig

        if not await AntiCheatConfig.is_enabled(message.guild):
            return False

        # メンションスパム検知が無効な場合は処理しない
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
                return await MentionSpam.block_and_notify(
                    message,
                    uid,
                    now,
                    "mention",
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
            content_token_spam_map[matched_key].popleft()
        # 3人以上が同一内容または高類似度内容を短時間で送信 or uuid4が2つ以上含まれる
        user_ids = set(uid for t, uid in content_token_spam_map[matched_key])
        if len(user_ids) >= TOKEN_SPAM_THRESHOLD or uuid4_count >= 2:
            for t, uid in content_token_spam_map[matched_key]:
                user_blocked_until[uid] = now + BLOCK_DURATION
            from .notifier import Notifier

            await Notifier(message).purge_user_messages(alert_type="token")
            try:
                await message.author.timeout(
                    duration=timeout_duration,
                    reason="Token/Webhookスパム検知による自動タイムアウト",
                )
            except Exception:
                pass
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
        # AntiCheat全体が無効な場合は処理しない
        from .config import AntiCheatConfig

        if not await AntiCheatConfig.is_enabled(message.guild):
            return False

        # タイムベーススパム検知が無効な場合は処理しない
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
                    return await TimebaseSpam.block_and_notify(
                        message,
                        uid,
                        now,
                        "timebase",
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
