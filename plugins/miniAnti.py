import difflib
import asyncio
from discord.ext import commands
import discord
from datetime import timedelta
import re

# 類似メッセージのしきい値
SIMILARITY_THRESHOLD = 0.85
# 直近何件のメッセージを比較するか
RECENT_MSG_COUNT = 5
# スパム判定でブロックする秒数
BLOCK_DURATION = 5 * 60



#| キー名                        | 意味・用途                                                  
#|-------------------------------|------------------------------------------------------------
#| base_threshold                | スパム判定の基本となるスコア閾値（これ以上でスパムと判定）       
#| high_similarity_threshold     | メッセージ類似度が「高」とみなすしきい値（0.9以上）              
#| high_similarity_score         | 高類似度の場合に加算されるスコア                                 
#| medium_similarity_threshold   | メッセージ類似度が「中」とみなすしきい値（0.75以上）             
#| medium_similarity_score       | 中類似度の場合に加算されるスコア                                 
#| low_similarity_threshold      | メッセージ類似度が「低」とみなすしきい値（0.6以上）              
#| low_similarity_score          | 低類似度の場合に加算されるスコア                                 
#| rapid_post_threshold          | 直前投稿からこの秒数未満なら「超高速連投」と判定                 
#| rapid_post_score              | 超高速連投時に加算されるスコア                                   
#| fast_post_threshold           | 直前投稿からこの秒数未満なら「高速連投」と判定                   
#| fast_post_score               | 高速連投時に加算されるスコア                                     
#| random_text_score             | ランダム性が高いテキスト（意味不明な文字列等）に加算されるスコア 
#| repetitive_char_score         | 同じ文字やパターンの繰り返しが多い場合に加算されるスコア         
#| no_vowel_score                | 母音が極端に少ない場合に加算されるスコア                         
#| very_long_threshold           | メッセージがこの文字数を超えると「非常に長い」と判定             
#| very_long_score               | 非常に長いメッセージに加算されるスコア                           
#| long_threshold                | メッセージがこの文字数を超えると「長い」と判定                   
#| long_score                    | 長いメッセージに加算されるスコア                                 
#| very_short_threshold          | メッセージがこの文字数以下だと「非常に短い」と判定               
#| very_short_score              | 非常に短いメッセージに加算されるスコア                           
#| high_symbol_threshold         | 記号率がこの割合を超えると「記号だらけ」と判定                   
#| high_symbol_score             | 記号だらけのメッセージに加算されるスコア                         
#| medium_symbol_threshold       | 記号率がこの割合を超えると「記号多め」と判定                     
#| medium_symbol_score           | 記号多めのメッセージに加算されるスコア                           
#| japanese_text_reduction       | 日本語中心のテキストの場合、ランダム性スコア等を減点する割合     
#| burst_count_threshold         | 指定秒数内にこの回数以上投稿すると「バースト投稿」と判定         
#| burst_window                  | バースト投稿判定のための時間窓（秒）                             
#| burst_score                   | バースト投稿時に加算されるスコア                                 

# テキストスパム検知の詳細設定
TEXT_SPAM_CONFIG = {
    # 基本閾値
    "base_threshold": 0.8,
    # 高類似度の閾値とスコア
    "high_similarity_threshold": 0.9,
    "high_similarity_score": 0.6,
    "medium_similarity_threshold": 0.75,
    "medium_similarity_score": 0.35,
    "low_similarity_threshold": 0.6,
    "low_similarity_score": 0.15,
    # 連投間隔のスコア
    "rapid_post_threshold": 1.0,
    "rapid_post_score": 0.4,
    "fast_post_threshold": 2.0,
    "fast_post_score": 0.2,
    # ランダム性スコア調整
    "random_text_score": 0.35,
    "repetitive_char_score": 0.4,
    "no_vowel_score": 0.3,
    # 長さによるスコア調整
    "very_long_threshold": 500,
    "very_long_score": 0.3,
    "long_threshold": 300,
    "long_score": 0.15,
    "very_short_threshold": 2,
    "very_short_score": 0.25,
    # 記号率スコア調整
    "high_symbol_threshold": 0.7,
    "high_symbol_score": 0.3,
    "medium_symbol_threshold": 0.5,
    "medium_symbol_score": 0.15,
    # 日本語文字の重み（誤検知を減らすため）
    "japanese_text_reduction": 0.2,
    # 短時間での連続投稿カウント
    "burst_count_threshold": 4,
    "burst_window": 10,
    "burst_score": 0.5,
}

# ユーザーごとの直近メッセージ履歴とブロック情報
user_recent_messages = {}
user_blocked_until = {}

# メディアスパム検知用
IMAGE_SPAM_THRESHOLD = 3  # 直近何件の画像・動画投稿でスパム判定するか
IMAGE_SPAM_WINDOW = 30  # 秒
user_image_timestamps = {}

# メンションスパム検知用
MENTION_SPAM_THRESHOLD = 3  # 直近何件のメンション投稿でスパム判定するか
MENTION_SPAM_WINDOW = 30  # 秒
user_mention_timestamps = {}

# タイムベース検知用: 各ユーザーの送信時刻履歴
user_time_intervals = {}

# Token/Webhookスパム検知用: content→[(timestamp, user_id)]リスト
TOKEN_SPAM_WINDOW = 5  # 秒
TOKEN_SPAM_THRESHOLD = 3  # 3人目で検知
content_token_spam_map = {}


class Notifier:
    def __init__(self, message):
        self.message = message

    async def send_image_spam_warning(self):
        embed = discord.Embed(
            title="画像スパム警告",
            description="⚠️ 画像によるスパム行為が検出されたため、一時的にチャットが制限されます。約30分後に解除されます。",
            color=0xF59E42,
        )
        try:
            await self.message.reply(embed=embed, ephemeral=True)
        except Exception:
            pass

    async def purge_user_messages(self, alert_type="text", deleted=None):
        """
        アンチチートで検知された全ての処理で共通: 直近1時間以内のユーザーのメッセージを最大10件削除し、DMでEmbed通知（クールタイム付き）
        alert_type: 'text' or 'image' など警告種別
        deleted: Noneまたはint。Noneなら削除処理を行い、intならその件数で通知のみ
        """
        try:
            from datetime import datetime, timezone, timedelta as dt_timedelta

            deleted_count = 0
            channel = self.message.channel
            now = datetime.now(timezone.utc)
            # 削除件数が指定されていなければ実際に削除
            if deleted is None:
                DELETE_LIMIT = 10
                count = 0
                async for msg in channel.history(limit=100):
                    if msg.author.id == self.message.author.id:
                        if (
                            msg.created_at
                            and (now - msg.created_at).total_seconds() <= 3600
                        ):
                            try:
                                await msg.delete()
                                deleted_count += 1
                                count += 1
                                await asyncio.sleep(1.2)
                                if count >= DELETE_LIMIT:
                                    break
                            except Exception:
                                pass
            else:
                deleted_count = deleted
            # DM通知（Embed形式・クールタイム付き）
            if not hasattr(self, "_last_dm_notify"):
                self._last_dm_notify = 0
            dm_cooldown = 60
            now_ts = now.timestamp()
            # クールタイム中はDMを送らず削除のみ行う
            if now_ts - getattr(self, "_last_dm_notify", 0) > dm_cooldown:
                try:
                    embed_dm = discord.Embed(
                        title="警告: 荒らし行為",
                        description=(
                            f"あなたの荒らし行為が検知されました。\n"
                            f"Type: {alert_type}\n"
                            f"直近1時間以内のメッセージ{deleted_count}件が削除されました。\n"
                            f"チャンネル: {channel.mention}\n"
                            "今後同様の行為が続く場合、より厳しい措置が取られる可能性があります。"
                        ),
                        color=0xA21CAF,
                    )
                    await self.message.author.send(embed=embed_dm)
                    print(f"[miniAnti] DM送信: user={self.message.author} id={self.message.author.id} type={alert_type} deleted={deleted_count}")
                    self._last_dm_notify = now_ts
                except Exception:
                    pass
            # クールタイム中は何も送らない
        except Exception:
            pass


class MiniAntiBypass:
    @staticmethod
    def should_bypass(message):
        if message.guild:
            from DataBase import get_guild_value

            bypass_role_id = get_guild_value(message.guild.id, "miniAntiBypassRole")
            if bypass_role_id:
                try:
                    bypass_role_id = int(bypass_role_id)
                except Exception:
                    pass
                if any(
                    getattr(r, "id", None) == bypass_role_id
                    for r in getattr(message.author, "roles", [])
                ):
                    return True
        return False


def is_random_spam(text):
    import re

    if len(text) > 20:
        non_jp = re.sub(r"[\u3040-\u30ff\u4e00-\u9fff]", "", text)
        if len(non_jp) / len(text) > 0.8:
            return True
        if re.fullmatch(r"(.)\1{7,}", text) or re.fullmatch(r"(..)(\1){5,}", text):
            return True
        if re.fullmatch(r"[A-Za-z0-9]{15,}", text):
            return True
        vowels = "aeiouあいうえお"
        v_count = sum(1 for c in text if c in vowels)
        if v_count / len(text) < 0.2:
            return True
    return False


class MiniAnti:
    @staticmethod
    def _is_japanese_heavy(text):
        """テキストが日本語中心かどうかを判定"""
        if not text:
            return False
        import re
        # ひらがな、カタカナ、漢字の文字数をカウント
        japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text))
        return japanese_chars / len(text) > 0.3

    @staticmethod
    def _count_burst_messages(history, now, window=10):
        """指定時間内の連続投稿数をカウント"""
        if not history:
            return 0
        count = 1  # 現在のメッセージを含む
        for old_msg in reversed(history):
            old_time = old_msg[1] if isinstance(old_msg, tuple) else 0
            if now - old_time <= window:
                count += 1
            else:
                break
        return count

    @staticmethod
    def _score_similarity(message, history, now):
        """改良された類似度スコア計算"""
        if not history:
            return 0
        
        config = TEXT_SPAM_CONFIG
        max_score = 0
        content = message.content.strip()
        
        # 短すぎるメッセージの類似度は重要視しない
        if len(content) < 5:
            return 0
        
        for old_msg in history:
            old_content, old_time = old_msg if isinstance(old_msg, tuple) else (old_msg, 0)
            old_content = old_content.strip()
            
            # 同じ内容の場合は確実にスパム
            if content == old_content:
                return config["high_similarity_score"]
            
            ratio = difflib.SequenceMatcher(None, old_content, content).ratio()
            time_diff = abs(now - old_time)
            
            # 時間が近いほど重要視
            time_weight = 1.0 if time_diff < 5 else 0.8 if time_diff < 15 else 0.6
            
            if ratio >= config["high_similarity_threshold"]:
                score = config["high_similarity_score"] * time_weight
            elif ratio >= config["medium_similarity_threshold"]:
                score = config["medium_similarity_score"] * time_weight
            elif ratio >= config["low_similarity_threshold"]:
                score = config["low_similarity_score"] * time_weight
            else:
                score = 0
            
            max_score = max(max_score, score)
        
        return max_score

    @staticmethod
    def _score_randomness(message):
        """改良されたランダム性スコア計算"""
        text = message.content.strip()
        if len(text) < 3:  # 短いテキストはランダム判定しない
            return 0
        
        config = TEXT_SPAM_CONFIG
        score = 0
        
        import re
        
        # 日本語が多い場合はランダム性スコアを軽減
        is_jp_heavy = MiniAnti._is_japanese_heavy(text)
        reduction = config["japanese_text_reduction"] if is_jp_heavy else 0
        
        # 非日本語文字の比率（改良）
        if len(text) > 15:
            non_jp = re.sub(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\s]', '', text)
            if len(non_jp) / len(text) > 0.8:
                score += config["random_text_score"] - reduction
        
        # 繰り返し文字パターン（より厳密に）
        if re.search(r'(.)\1{8,}', text):  # 同じ文字9回以上
            score += config["repetitive_char_score"]
        elif re.search(r'(.{2,3})\1{4,}', text):  # 2-3文字の繰り返し5回以上
            score += config["repetitive_char_score"]
        
        # 英数字のみの長い文字列
        if len(text) > 20 and re.fullmatch(r'[A-Za-z0-9\s]{20,}', text):
            # ただし、意味のある英単語が含まれている場合は軽減
            words = re.findall(r'[A-Za-z]{3,}', text)
            if len(words) < 3:  # 英単語が少ない場合のみペナルティ
                score += config["random_text_score"] - reduction
        
        # 母音の比率（改良）
        if len(text) > 15:
            vowels = 'aeiouあいうえおAEIOU'
            consonants = 'bcdfghjklmnpqrstvwxyzかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん'
            vowel_count = sum(1 for c in text if c in vowels)
            consonant_count = sum(1 for c in text if c in consonants)
            
            if consonant_count > 0:
                vowel_ratio = vowel_count / (vowel_count + consonant_count)
                if vowel_ratio < 0.15:  # 極端に母音が少ない
                    score += config["no_vowel_score"] - reduction
        
        return min(score, 0.5)  # 最大値を制限

    @staticmethod
    def _score_length(message):
        """改良された長さスコア計算"""
        content = message.content.strip()
        length = len(content)
        config = TEXT_SPAM_CONFIG
        
        # 極端に長い
        if length > config["very_long_threshold"]:
            return config["very_long_score"]
        elif length > config["long_threshold"]:
            return config["long_score"]
        
        # 極端に短い（ただし絵文字のみなどは除外）
        if length <= config["very_short_threshold"]:
            # 絵文字や日本語文字が含まれている場合は軽減
            import re
            if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]', content):
                return 0
            return config["very_short_score"]
        
        return 0

    @staticmethod
    def _score_symbol_ratio(message):
        """改良された記号率スコア計算"""
        text = message.content.strip()
        if not text:
            return 0
        
        config = TEXT_SPAM_CONFIG
        import re
        
        # 基本的な記号をカウント（日本語の句読点は除外）
        symbols = re.findall(r'[!@#$%^&*()_+=\[\]{}|\\:";\'<>?/~`\-]', text)
        symbol_count = len(symbols)
        
        # 絵文字は記号としてカウントしない
        emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]')
        text_without_emoji = emoji_pattern.sub('', text)
        
        if len(text_without_emoji) == 0:
            return 0
        
        symbol_ratio = symbol_count / len(text_without_emoji)
        
        if symbol_ratio > config["high_symbol_threshold"]:
            return config["high_symbol_score"]
        elif symbol_ratio > config["medium_symbol_threshold"]:
            return config["medium_symbol_score"]
        
        return 0

    @staticmethod
    def _score_burst_posting(history, now):
        """短時間での連続投稿スコア"""
        config = TEXT_SPAM_CONFIG
        burst_count = MiniAnti._count_burst_messages(history, now, config["burst_window"])
        
        if burst_count >= config["burst_count_threshold"]:
            return config["burst_score"]
        
        return 0

    @staticmethod
    async def check_and_block_spam(message):
        # コマンドチェック
        if hasattr(message, "content") and message.content.startswith("#"):
            from index import isCommand
            cmd_name = message.content[1:].split()[0]
            if isCommand(cmd_name):
                return False
        
        # バイパスチェック
        if MiniAntiBypass.should_bypass(message):
            return False
        
        # メディアのみメッセージはスキップ
        media_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".mp4", ".mov", ".avi", ".wmv", ".webm", ".mkv")
        only_media = False
        if hasattr(message, "attachments") and message.attachments:
            if all(any(att.filename.lower().endswith(ext) for ext in media_exts) for att in message.attachments):
                content = getattr(message, "content", "")
                if not content or re.fullmatch(r'(https?://\S+\s*)+', content):
                    only_media = True
        if only_media:
            return False
        
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        history = user_recent_messages.get(user_id, [])
        
        # 設定読み込み
        config = TEXT_SPAM_CONFIG
        
        # スコアリング（改良版）
        score = 0
        
        # 各スコア要素を計算
        similarity_score = MiniAnti._score_similarity(message, history, now)
        randomness_score = MiniAnti._score_randomness(message)
        length_score = MiniAnti._score_length(message)
        symbol_score = MiniAnti._score_symbol_ratio(message)
        burst_score = MiniAnti._score_burst_posting(history, now)
        
        # 連投間隔スコア（改良版）
        interval_score = 0
        if history:
            last_time = history[-1][1] if isinstance(history[-1], tuple) else 0
            interval = now - last_time
            
            if interval < config["rapid_post_threshold"]:
                interval_score = config["rapid_post_score"]
            elif interval < config["fast_post_threshold"]:
                interval_score = config["fast_post_score"]
        
        # 総合スコア計算
        score = similarity_score + randomness_score + length_score + symbol_score + interval_score + burst_score
        
        # 日本語中心のテキストの場合、閾値を少し上げる（誤検知防止）
        threshold = config["base_threshold"]
        if MiniAnti._is_japanese_heavy(message.content):
            threshold += 0.1
        
        # 履歴更新
        history.append((message.content, now))
        if len(history) > RECENT_MSG_COUNT:
            history = history[-RECENT_MSG_COUNT:]
        user_recent_messages[user_id] = history
        
        # デバッグ情報（開発用）
        # print(f"[miniAnti] user={message.author.id} score={score:.2f} threshold={threshold:.2f} sim={similarity_score:.2f} rand={randomness_score:.2f} len={length_score:.2f} sym={symbol_score:.2f} int={interval_score:.2f} burst={burst_score:.2f}")
        
        # 判定
        if score >= threshold:
            user_blocked_until[user_id] = now + BLOCK_DURATION
            user_recent_messages[user_id] = []
            try:
                if hasattr(message.author, "timed_out_until"):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(until, reason="miniAnti: テキストスパムスコア検出")
                notifier = Notifier(message)
                await notifier.purge_user_messages(alert_type="text")
            except Exception:
                pass
            return True
        
        return False

    @staticmethod
    async def check_and_block_media_spam(message):
        if MiniAntiBypass.should_bypass(message):
            return False
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        media_exts = (
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".bmp",
            ".webp",
            ".mp4",
            ".mov",
            ".avi",
            ".wmv",
            ".webm",
            ".mkv",
        )
        media_count = 0
        # 添付ファイルの判定
        for att in message.attachments:
            if any(att.filename.lower().endswith(ext) for ext in media_exts):
                media_count += 1
        # メッセージ本文のgif URLも判定（点滅gif検出は廃止）
        if media_count == 0:
            return False
        timestamps = user_image_timestamps.get(user_id, [])
        timestamps = [t for t in timestamps if now - t < IMAGE_SPAM_WINDOW]
        timestamps.extend([now] * media_count)
        user_image_timestamps[user_id] = timestamps
        if len(timestamps) >= IMAGE_SPAM_THRESHOLD:
            user_blocked_until[user_id] = now + BLOCK_DURATION
            user_recent_messages[user_id] = []
            user_image_timestamps[user_id] = []
            try:
                if hasattr(message.author, "timed_out_until"):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(
                        until, reason="miniAnti: メディアスパム検出"
                    )
                notifier = Notifier(message)
                await notifier.purge_user_messages(alert_type="image")
            except Exception:
                pass
            return True
        return False

    @staticmethod
    async def check_and_block_mention_spam(message):
        if MiniAntiBypass.should_bypass(message):
            return False
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        mention_count = len(message.mentions)
        # メンションがなければスルー
        if mention_count == 0:
            return False
        timestamps = user_mention_timestamps.get(user_id, [])
        timestamps = [t for t in timestamps if now - t < MENTION_SPAM_WINDOW]
        timestamps.extend([now] * mention_count)
        user_mention_timestamps[user_id] = timestamps
        if len(timestamps) >= MENTION_SPAM_THRESHOLD:
            user_blocked_until[user_id] = now + BLOCK_DURATION
            user_recent_messages[user_id] = []
            user_mention_timestamps[user_id] = []
            try:
                if hasattr(message.author, "timed_out_until"):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(
                        until, reason="miniAnti: メンションスパム検出"
                    )
                notifier = Notifier(message)
                await notifier.purge_user_messages(alert_type="mention")
            except Exception:
                pass
            return True
        return False

    @staticmethod
    async def check_and_block_token_spam(message):
        """
        複数ユーザーがほぼ同時に同じ内容を送信した場合のToken/Webhookスパム検知
        2人までは許容、3人目で検知
        """
        if MiniAntiBypass.should_bypass(message):
            return False
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        content = message.content.strip()
        if not content or len(content) < 5:
            return False
        # 絵文字や記号だけの一致は除外
        import re
        if re.fullmatch(r'[\W_]+', content):
            return False
        # 管理用リストの更新
        global content_token_spam_map
        entries = content_token_spam_map.get(content, [])
        # 古いエントリを除外
        entries = [(t, uid) for t, uid in entries if now - t < TOKEN_SPAM_WINDOW]
        # 既に同じユーザーが直近で送信していれば追加しない
        if any(uid == user_id for t, uid in entries):
            content_token_spam_map[content] = entries
            return False
        entries.append((now, user_id))
        content_token_spam_map[content] = entries
        if len(entries) >= TOKEN_SPAM_THRESHOLD:
            # 検知: 直近TOKEN_SPAM_WINDOW秒以内に3人以上が同じ内容
            for t, uid in entries:
                user_blocked_until[uid] = now + BLOCK_DURATION
                user_recent_messages[uid] = []
            try:
                if hasattr(message.author, "timed_out_until"):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(until, reason="miniAnti: Token/Webhookスパム検知")
                notifier = Notifier(message)
                await notifier.purge_user_messages(alert_type="token")
            except Exception:
                pass
            return True
        return False

    @staticmethod
    async def check_and_block_timebase_spam(message, min_msgs=8, var_threshold=0.15, hist_threshold=0.7, max_history=15, reset_interval=60, similarity_threshold=0.85):
        """
        interval_count: 直近何件の間隔で判定するか
        min_msgs: 判定に必要な最小メッセージ数
        var_threshold: 分散がこの値未満なら周期的とみなす
        hist_threshold: 1binに偏る割合がこの値以上なら周期的とみなす
        max_history: 履歴保存上限
        reset_interval: リセット間隔（秒）
        similarity_threshold: 類似性判定のしきい値
        """
        # サーバー参加から1週間以内のユーザーのみ有効化
        joined = getattr(message.author, 'joined_at', None)
        if joined is not None:
            from datetime import datetime, timezone
            now_dt = datetime.now(timezone.utc)
            if (now_dt - joined).total_seconds() > 86400 * 7:
                return False
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        times = user_time_intervals.get(user_id, [])
        # リセット機構: 最後のメッセージから一定時間経過した場合、履歴をリセット
        if times and now - times[-1] > reset_interval:
            times = []
        times.append(now)
        if len(times) > max_history:
            times = times[-max_history:]
        user_time_intervals[user_id] = times
        if len(times) < min_msgs:
            return False
        # 送信間隔リスト
        intervals = [t2 - t1 for t1, t2 in zip(times[:-1], times[1:])]
        if not intervals or min(intervals) <= 0:
            return False
        mean = sum(intervals) / len(intervals)
        var = sum((x - mean) ** 2 for x in intervals) / len(intervals)
        bin_edges = [0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        bins = [0] * (len(bin_edges))
        for interval in intervals:
            for i, edge in enumerate(bin_edges):
                if interval < edge:
                    bins[i] += 1
                    break
            else:
                bins[-1] += 1
        max_bin_ratio = max(bins) / len(intervals)
        # 類似性判定: 直近max_history件のメッセージで高類似度が多い場合のみスパムとみなす
        history = user_recent_messages.get(user_id, [])
        similar_count = 0
        if hasattr(message, "content") and history:
            import difflib
            for old_msg in history[-max_history:]:
                old_content, _ = old_msg if isinstance(old_msg, tuple) else (old_msg, 0)
                ratio = difflib.SequenceMatcher(None, old_content, message.content).ratio()
                if ratio >= similarity_threshold:
                    similar_count += 1
        # 直近のうち半分以上が高類似ならスパム判定対象
        is_similar_spam = similar_count >= max(2, len(history[-max_history:]) // 2)
        # 連続検知カウンタ
        if not hasattr(MiniAnti, '_timebase_detect_count'):
            MiniAnti._timebase_detect_count = {}
        detect_count = MiniAnti._timebase_detect_count.get(user_id, 0)
        # 判定
        if (var < var_threshold or max_bin_ratio > hist_threshold) and is_similar_spam:
            detect_count += 1
        else:
            detect_count = 0
        MiniAnti._timebase_detect_count[user_id] = detect_count
        if detect_count < 2:
            return False
        user_blocked_until[user_id] = now + BLOCK_DURATION
        user_recent_messages[user_id] = []
        user_time_intervals[user_id] = []
        MiniAnti._timebase_detect_count[user_id] = 0
        try:
            if hasattr(message.author, "timed_out_until"):
                until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                await message.author.timeout(until, reason="miniAnti: タイムベーススパム検出")
            notifier = Notifier(message)
            await notifier.purge_user_messages(alert_type="timebase")
        except Exception:
            pass
        return True

    @staticmethod
    async def is_user_blocked(message):
        if MiniAntiBypass.should_bypass(message):
            return False
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        # タイムアウト中かどうかも判定
        if user_id in user_blocked_until and now < user_blocked_until[user_id]:
            # すでにタイムアウト中なら何もしない
            if (
                hasattr(message.author, "timed_out_until")
                and message.author.timed_out_until
            ):
                return True
            # まだタイムアウトが付与されていなければ付与
            try:
                until = discord.utils.utcnow() + timedelta(
                    seconds=int(user_blocked_until[user_id] - now)
                )
                await message.author.timeout(
                    until, reason="miniAnti: スパム/荒らし検知による自動タイムアウト"
                )
                # タイムアウト付与時に履歴もクリア（解除時と同じ挙動）
                user_recent_messages[user_id] = []
                user_time_intervals[user_id] = []
                if hasattr(MiniAnti, '_timebase_detect_count'):
                    MiniAnti._timebase_detect_count[user_id] = 0
            except Exception:
                pass
            return True
        return False

    @staticmethod
    async def handle_unblock(user_id):
        # アンブロック時にも履歴をクリア
        user_recent_messages[user_id] = []
        user_time_intervals[user_id] = []
        if hasattr(MiniAnti, '_timebase_detect_count'):
            MiniAnti._timebase_detect_count[user_id] = 0

    @staticmethod
    async def handle_griefing(message, alert_type="text"):
        # blockword系のアラートDM送信は不要なので何もしない
        if alert_type == "blockword":
            return
        notifier = Notifier(message)
        await notifier.purge_user_messages(alert_type=alert_type)
        # --- アラートチャンネル通知 ---
        try:
            # guildDatabaseからalertチャンネルIDを取得
            alert_channel_id = await MiniAnti.load_guild_json(message.guild, "miniAntiAlertChannel")
            if alert_channel_id:
                channel = message.guild.get_channel(alert_channel_id)
                if channel:
                    embed = discord.Embed(
                        title="miniAnti 警告通知",
                        description=f"荒らし行為が検知されました。\nType: {alert_type}\nUser: {message.author.mention} ({message.author.id})\nChannel: {message.channel.mention}",
                        color=0xFF5555,
                        timestamp=discord.utils.utcnow()
                    )
                    await channel.send(embed=embed)
        except Exception:
            pass

    @staticmethod
    async def save_guild_json(guild, key, value):
        """
        GuildDatabaseカテゴリを使ってギルドごとのjsonデータをまとめて管理・保存する
        key: 保存するデータのキー名
        value: 保存する値（dictやstrなどjson化できるもの）
        """
        import json
        from DataBase import GuildDatabase
        # チャンネル名はkeyで一意に
        channel_name = f"{key}"
        content = json.dumps({key: value}, ensure_ascii=False, indent=2)
        # 既存チャンネルがあれば削除
        db_channels = await GuildDatabase.get_db_channels(guild)
        for ch in db_channels:
            if ch.name == f"db-{channel_name}":
                await ch.delete(reason="GuildDatabase: 上書き保存")
        # 新規作成
        await GuildDatabase.create_db_channel(guild, channel_name, content)

    @staticmethod
    async def load_guild_json(guild, key):
        """
        GuildDatabaseカテゴリからkeyに対応するjsonデータを取得
        """
        import json
        from DataBase import GuildDatabase
        channel_name = f"db-{key}"
        db_channels = await GuildDatabase.get_db_channels(guild)
        for ch in db_channels:
            if ch.name == channel_name:
                async for msg in ch.history(limit=1, oldest_first=True):
                    try:
                        data = json.loads(msg.content)
                        return data.get(key)
                    except Exception:
                        return None
        return None


def setup(bot):
    @bot.listen("on_message")
    async def miniAnti_on_message(message):
        if message.author.bot or not message.guild:
            return
        # Token/Webhookスパム判定（最優先）
        token_blocked = await MiniAnti.check_and_block_token_spam(message)
        if token_blocked:
            await MiniAnti.handle_griefing(message, alert_type="token")
            try:
                await message.delete()
            except:
                pass
            return
        # ブロック中ならタイムアウトを活用し削除
        if await MiniAnti.is_user_blocked(message):
            try:
                await message.delete()
            except:
                pass
            return
        # 画像・動画スパム判定
        media_blocked = await MiniAnti.check_and_block_media_spam(message)
        if media_blocked:
            await MiniAnti.handle_griefing(message, alert_type="image")
            try:
                await message.delete()
            except:
                pass
            return
        # メンションスパム判定
        mention_blocked = await MiniAnti.check_and_block_mention_spam(message)
        if mention_blocked:
            await MiniAnti.handle_griefing(message, alert_type="mention")
            try:
                await message.delete()
            except:
                pass
            return
        # タイムベース検知を追加
        timebase_blocked = await MiniAnti.check_and_block_timebase_spam(message)
        if timebase_blocked:
            await MiniAnti.handle_griefing(message, alert_type="timebase")
            try:
                await message.delete()
            except:
                pass
            return
        # テキストスパム判定（類似性）
        blocked = await MiniAnti.check_and_block_spam(message)
        if blocked:
            await MiniAnti.handle_griefing(message, alert_type="text")
            try:
                await message.delete()
            except:                pass
            return

    @commands.command()
    async def anti(ctx):
        """
        miniAnti : サーバーのスパム・荒らし対策コマンド

        #anti settings: 現在の設定をEmbedで表示
        #anti bypass <roleID>: 指定ロールをbypass（スパム判定除外）に設定（管理者のみ）
        #anti unblock <ユーザーID>: 指定ユーザーのblock/タイムアウトを解除（管理者のみ）
        #anti block <ユーザーID> <期間>: 指定ユーザーを任意期間ブロック（例: 1m, 2h, 3d, 10s）（管理者のみ）
        #anti list: 現在ブロック中のユーザー一覧を表示
        #anti test <テキスト>: 指定したテキストのスパムスコアを表示（管理者のみ）

        詳細は #help で確認できます。
        """
        # コマンド引数のパース
        args = ctx.message.content.split()
        subcmd = args[1] if len(args) > 1 else ""
        arg = args[2] if len(args) > 2 else ""
        
        if subcmd.lower() in ["config", "test"]:
            await ctx.send("❌ この設定はコードでのみ変更可能です。管理者が直接コードを編集してください。", delete_after=15)
            return
        
        elif subcmd.lower() == "bypass":
            if not ctx.guild:
                await ctx.send("❌ サーバー内でのみ実行可能です。", delete_after=10)
                return
            from DataBase import get_guild_value, update_guild_data

            # 管理者判定（従来のis_admin→管理者権限で判定）
            from index import is_admin, load_config

            config = load_config()
            if not is_admin(str(ctx.author.id), ctx.guild.id, config):
                await ctx.send("❌ 管理者のみ実行可能です。", delete_after=10)
                return
            if not arg.isdigit():
                await ctx.send(
                    "ロールIDを指定してください。例: #minianti bypass 123456789012345678",
                    delete_after=10,
                )
                return
            role_id = int(arg)
            role = ctx.guild.get_role(role_id)
            if not role:
                await ctx.send("指定したロールが見つかりません。", delete_after=10)
                return
            update_guild_data(ctx.guild.id, "miniAntiBypassRole", role_id)
            await ctx.send(
                f"✅ このサーバーのminiAnti bypassロールを `{role.name}` (ID: {role_id}) に設定しました。",
                delete_after=10,
            )
            return
        if subcmd.lower() == "unblock":
            if not ctx.guild:
                await ctx.send("❌ サーバー内でのみ実行可能です。", delete_after=10)
                return
            from index import is_admin, load_config

            config = load_config()
            if not is_admin(str(ctx.author.id), ctx.guild.id, config):
                await ctx.send("❌ 管理者のみ実行可能です。", delete_after=10)
                return
            if not arg.isdigit():
                await ctx.send(
                    "ユーザーIDを指定してください。例: #minianti unblock 123456789012345678",
                    delete_after=10,
                )
                return
            user_id = int(arg)
            member = ctx.guild.get_member(user_id)
            # miniAntiの内部block解除
            if user_id in user_blocked_until:
                del user_blocked_until[user_id]
            # Discordのタイムアウト解除
            if member:
                try:
                    await member.edit(
                        timed_out_until=None, reason="miniAnti: 管理者による手動unblock"
                    )
                except Exception:
                    pass
            await ctx.send(
                f"✅ ユーザーID `{user_id}` のblock/タイムアウトを解除しました。",
                delete_after=10,
            )
            # アンブロック時にも履歴をクリア
            try:
                await MiniAnti.handle_unblock(user_id)
            except Exception:
                pass
            return
        if subcmd.lower() == "block":
            if not ctx.guild:
                await ctx.send("❌ サーバー内でのみ実行可能です。", delete_after=10)
                return
            from index import is_admin, load_config

            config = load_config()
            if not is_admin(str(ctx.author.id), ctx.guild.id, config):
                await ctx.send("❌ 管理者のみ実行可能です。", delete_after=10)
                return
            args = arg.split()
            if len(args) < 2 or not args[0].isdigit():
                await ctx.send(
                    "ユーザーIDと期間を指定してください。例: #minianti block 123456789012345678 1m",
                    delete_after=10,
                )
                return
            user_id = int(args[0])
            duration_str = args[1]
            import re

            m = re.match(r"(\d+)([smhd])", duration_str)
            if not m:
                await ctx.send(
                    "期間の形式が不正です。例: 1m, 2h, 3d, 10s", delete_after=10
                )
                return
            num, unit = int(m.group(1)), m.group(2)
            seconds = num * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
            now = asyncio.get_event_loop().time()
            user_blocked_until[user_id] = now + seconds
            member = ctx.guild.get_member(user_id)
            if member:
                try:
                    until = discord.utils.utcnow() + timedelta(seconds=seconds)
                    await member.timeout(
                        until, reason="miniAnti: 管理者による手動block"
                    )
                except Exception:
                    pass
            await ctx.send(
                f"✅ ユーザーID `{user_id}` を {duration_str} ブロックしました。",
                delete_after=10,
            )
            return
        if subcmd.lower() == "list":
            now = asyncio.get_event_loop().time()
            blocked = [
                (uid, until) for uid, until in user_blocked_until.items() if until > now
            ]
            if not blocked:
                await ctx.send("現在ブロック中のユーザーはいません。", delete_after=10)
                return
            embed = discord.Embed(
                title="miniAnti ブロック中ユーザー一覧", color=0xA21CAF
            )
            for uid, until in blocked:
                left = int(until - now)
                m, s = divmod(left, 60)
                h, m = divmod(m, 60)
                d, h = divmod(h, 24)
                if d:
                    time_str = f"{d}d {h}h {m}m {s}s"
                elif h:
                    time_str = f"{h}h {m}m {s}s"
                elif m:
                    time_str = f"{m}m {s}s"
                else:
                    time_str = f"{s}s"
                embed.add_field(
                    name=f"ユーザーID: {uid}", value=f"残り: {time_str}", inline=False
                )
            await ctx.send(embed=embed)            
            return
        if subcmd.lower() == "alert":
            if not ctx.guild:
                await ctx.send("❌ サーバー内でのみ実行可能です。", delete_after=10)
                return
            from index import is_admin, load_config
            config = load_config()
            if not is_admin(str(ctx.author.id), ctx.guild.id, config):
                await ctx.send("❌ 管理者のみ実行可能です。", delete_after=10)
                return
            if not arg.isdigit():
                await ctx.send("チャンネルIDを指定してください。例: #anti alert 123456789012345678", delete_after=10)
                return
            channel_id = int(arg)
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                await ctx.send("指定したチャンネルが見つかりません。", delete_after=10)
                return
            # GuildDatabaseでalert設定を保存
            await MiniAnti.save_guild_json(ctx.guild, "miniAntiAlertChannel", channel_id)
            await ctx.send(f"✅ miniAntiのアラート通知チャンネルを <#{channel_id}> に設定し、guildDatabaseに保存しました。", delete_after=10)
            return
        if not subcmd:
            await ctx.send("`#help` でコマンド一覧・説明を確認できます。", delete_after=10)
            return
        else:
            await ctx.send("`#help` を参照してください。", delete_after=10)
