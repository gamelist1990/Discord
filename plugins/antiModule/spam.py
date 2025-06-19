import difflib
import time
from collections import deque
import asyncio
from datetime import datetime, timezone, timedelta

import discord
from plugins.antiModule.notifier import Notifier
from plugins.antiModule.bypass import MiniAntiBypass

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
    "repeat_phrase_min_length": 5,  # 繰り返しフレーズの最小長
    "repeat_phrase_min_count": 3,  # 繰り返し回数
    "repeat_phrase_score": 0.4,    # 繰り返しフレーズスコア
    "kana_symbol_run_length": 10,  # ひらがな・カタカナ・記号連続の最小長
    "kana_symbol_run_score": 0.3,  # そのスコア
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
    async def reset_slowmode_if_no_spam(channel, author_id, guild_id, reset_delay=60):
        """一定時間後に荒らしがなければslowmodeを元に戻す（必ず記録済み値に戻す）"""
        await asyncio.sleep(reset_delay)
        key = (guild_id, channel.id)
        # --- 元のslowmode値を取得 ---
        original_delay = 0
        if hasattr(BaseSpam, "_original_slowmode"):
            original_delay = BaseSpam._original_slowmode.get(key, 0)
        try:
            await channel.edit(slowmode_delay=original_delay)
        except Exception as e:
            print(f"[ERROR] Failed to reset slowmode: {e}")
        # --- 一度戻したら記録を削除 ---
        if hasattr(BaseSpam, "_original_slowmode"):
            BaseSpam._original_slowmode.pop(key, None)

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
                # --- 追加: 既存slowmode値を保存 ---
                key = (message.guild.id, message.channel.id)
                if not hasattr(BaseSpam, "_original_slowmode"):
                    BaseSpam._original_slowmode = {}
                # 保存されていなければ保存
                if key not in BaseSpam._original_slowmode:
                    try:
                        BaseSpam._original_slowmode[key] = message.channel.slowmode_delay
                    except Exception:
                        BaseSpam._original_slowmode[key] = 0

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
                reset_delay = 10  # 

                # --- slowmode解除時に元の値へ戻す ---
                task = asyncio.create_task(
                    BaseSpam.reset_slowmode_if_no_spam(
                        message.channel, message.author.id, message.guild.id, reset_delay
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
        self.guild_spam_counts = {}  # {guild_id: [(timestamp, user_id, alert_type), ...]}
        self.mass_spam_active = {}  # {guild_id: timestamp}
        self.processed_logs = set()  # 処理済みログのハッシュ

    def add_spam_log(self, guild_id, user_id, alert_type, timestamp):
        # ギルドIDが無効な場合は無視
        if guild_id is None:
            return

        # ログエントリの作成
        log_entry = (timestamp, user_id, alert_type)

        # バッファに追加
        self.log_buffer.append(log_entry)

        # ギルドごとのスパムログに追加
        if guild_id not in self.guild_spam_counts:
            self.guild_spam_counts[guild_id] = []
        self.guild_spam_counts[guild_id].append(log_entry)

        # 大人数スパム判定のための処理
        self.process_mass_spam(guild_id, log_entry)

    def process_mass_spam(self, guild_id, log_entry):
        # 現在のギルドのスパムログを取得
        guild_logs = self.guild_spam_counts.get(guild_id, [])

        # 一定数以上のスパムログがある場合に判定
        if len(guild_logs) >= MASS_SPAM_USER_THRESHOLD:
            # タイムスタンプでソート
            sorted_logs = sorted(guild_logs, key=lambda x: x[0])

            # 最初のログと最後のログの時間差を計算
            time_diff = sorted_logs[-1][0] - sorted_logs[0][0]

            # 時間差が閾値以下であれば大人数スパムとみなす
            if time_diff <= MASS_SPAM_DETECTION_WINDOW:
                self.activate_mass_spam_mode(guild_id)

    def activate_mass_spam_mode(self, guild_id):
        # 既にアクティブな場合は何もしない
        if guild_id in self.mass_spam_active:
            return

        # アクティブにする
        self.mass_spam_active[guild_id] = True

        # 一定時間後に自動で非アクティブにする
        asyncio.create_task(self.deactivate_mass_spam_mode(guild_id))

    async def deactivate_mass_spam_mode(self, guild_id):
        await asyncio.sleep(MASS_SPAM_ENHANCED_SLOWMODE)
        if guild_id in self.mass_spam_active:
            del self.mass_spam_active[guild_id]

    def is_mass_spam_active(self, guild_id):
        return guild_id in self.mass_spam_active

    def check_mass_spam(self, guild_id):
        # ギルドに関連するスパムログを取得
        guild_logs = self.guild_spam_counts.get(guild_id, [])

        # 一定数以上のスパムログがあり、かつ最初のログからの時間差が閾値以下であればスパムとみなす
        if len(guild_logs) >= MASS_SPAM_USER_THRESHOLD:
            sorted_logs = sorted(guild_logs, key=lambda x: x[0])
            time_diff = sorted_logs[-1][0] - sorted_logs[0][0]
            if time_diff <= MASS_SPAM_DETECTION_WINDOW:
                return True
        return False

    def get_recent_spam_summary(self, guild_id):
        # ギルドに関連するスパムログを取得
        guild_logs = self.guild_spam_counts.get(guild_id, [])

        # ユーザーごとのスパム回数をカウント
        user_counts = {}
        for _, user_id, _ in guild_logs:
            if user_id not in user_counts:
                user_counts[user_id] = 0
            user_counts[user_id] += 1

        # 結果を返す
        return {
            "total_logs": len(guild_logs),
            "unique_users": len(user_counts),
            "user_counts": user_counts,
        }


# グローバルなログ集約インスタンス
spam_log_aggregator = SpamLogAggregator()