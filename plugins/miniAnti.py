import difflib
import asyncio
from discord.ext import commands
import discord
from datetime import timedelta

# 類似メッセージのしきい値
SIMILARITY_THRESHOLD = 0.85
# 直近何件のメッセージを比較するか
RECENT_MSG_COUNT = 5
# スパム判定でブロックする秒数
BLOCK_DURATION = 1 * 60  # 30分

# ユーザーごとの直近メッセージ履歴とブロック情報
user_recent_messages = {}
user_blocked_until = {}

# 画像スパム検知用
IMAGE_SPAM_THRESHOLD = 3  # 直近何件の画像投稿でスパム判定するか
IMAGE_SPAM_WINDOW = 30   # 秒
user_image_timestamps = {}

class Notifier:
    def __init__(self, message):
        self.message = message

    async def send_image_spam_warning(self):
        embed = discord.Embed(
            title="画像スパム警告",
            description="⚠️ 画像によるスパム行為が検出されたため、一時的にチャットが制限されます。約30分後に解除されます。",
            color=0xF59E42
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
                        if msg.created_at and (now - msg.created_at).total_seconds() <= 3600:
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
            if not hasattr(self, '_last_dm_notify'):
                self._last_dm_notify = 0
            dm_cooldown = 60
            now_ts = now.timestamp()
            # クールタイム中はDMを送らず削除のみ行う
            if now_ts - getattr(self, '_last_dm_notify', 0) > dm_cooldown:
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
                        color=0xA21CAF
                    )
                    await self.message.author.send(embed=embed_dm)
                    self._last_dm_notify = now_ts
                except Exception:
                    pass
            # クールタイム中は何も送らない
        except Exception:
            pass

async def check_and_block_spam(message):
    user_id = message.author.id
    now = asyncio.get_event_loop().time()
    if user_id in user_blocked_until and now < user_blocked_until[user_id]:
        return True
    history = user_recent_messages.get(user_id, [])
    for old_msg in history:
        ratio = difflib.SequenceMatcher(None, old_msg, message.content).ratio()
        if ratio >= SIMILARITY_THRESHOLD:
            user_blocked_until[user_id] = now + BLOCK_DURATION
            user_recent_messages[user_id] = []
            try:
                if hasattr(message.author, 'timed_out_until'):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(until, reason="miniAnti: 類似スパム検出")
                notifier = Notifier(message)
                await notifier.purge_user_messages(alert_type="text")
            except Exception as e:
                pass
            return True
    history.append(message.content)
    if len(history) > RECENT_MSG_COUNT:
        history = history[-RECENT_MSG_COUNT:]
    user_recent_messages[user_id] = history
    return False

async def check_and_block_image_spam(message):
    user_id = message.author.id
    now = asyncio.get_event_loop().time()
    image_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")
    image_count = 0
    for att in message.attachments:
        if any(att.filename.lower().endswith(ext) for ext in image_exts):
            image_count += 1
    if image_count == 0:
        return False
    timestamps = user_image_timestamps.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < IMAGE_SPAM_WINDOW]
    timestamps.extend([now] * image_count)
    user_image_timestamps[user_id] = timestamps
    if len(timestamps) >= IMAGE_SPAM_THRESHOLD:
        user_blocked_until[user_id] = now + BLOCK_DURATION
        user_recent_messages[user_id] = []
        user_image_timestamps[user_id] = []
        try:
            if hasattr(message.author, 'timed_out_until'):
                until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                await message.author.timeout(until, reason="miniAnti: 画像スパム検出")
            notifier = Notifier(message)
            await notifier.purge_user_messages(alert_type="image")
        except Exception:
            pass
        return True
    return False

async def handle_griefing(message, alert_type="text"):
    notifier = Notifier(message)
    await notifier.purge_user_messages(alert_type=alert_type)

def setup(bot):
    @bot.listen('on_message')
    async def miniAnti_on_message(message):
        if message.author.bot or not message.guild:
            return
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        # ブロック中なら削除
        if user_id in user_blocked_until and now < user_blocked_until[user_id]:
            try:
                await message.delete()
            except:
                pass
            return
        # 画像スパム判定
        image_blocked = await check_and_block_image_spam(message)
        if image_blocked:
            await handle_griefing(message, alert_type="image")
            try:
                await message.delete()
            except:
                pass
            return
        # テキストスパム判定
        blocked = await check_and_block_spam(message)
        if blocked:
            await handle_griefing(message, alert_type="text")
            try:
                await message.delete()
            except:
                pass

