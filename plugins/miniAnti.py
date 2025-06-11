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

# ユーザーごとの直近メッセージ履歴とブロック情報
user_recent_messages = {}
user_blocked_until = {}

# メディアスパム検知用
IMAGE_SPAM_THRESHOLD = 3  # 直近何件の画像・動画投稿でスパム判定するか
IMAGE_SPAM_WINDOW = 30   # 秒
user_image_timestamps = {}

# メンションスパム検知用
MENTION_SPAM_THRESHOLD = 3  # 直近何件のメンション投稿でスパム判定するか
MENTION_SPAM_WINDOW = 30   # 秒
user_mention_timestamps = {}

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
                if any(getattr(r, 'id', None) == bypass_role_id for r in getattr(message.author, 'roles', [])):
                    return True
        return False

def is_random_spam(text):
    import re
    if len(text) > 20:
        non_jp = re.sub(r'[\u3040-\u30ff\u4e00-\u9fff]', '', text)
        if len(non_jp) / len(text) > 0.8:
            return True
        if re.fullmatch(r'(.)\1{7,}', text) or re.fullmatch(r'(..)(\1){5,}', text):
            return True
        if re.fullmatch(r'[A-Za-z0-9]{15,}', text):
            return True
        vowels = 'aeiouあいうえお'
        v_count = sum(1 for c in text if c in vowels)
        if v_count / len(text) < 0.2:
            return True
    return False

class MiniAnti:
    @staticmethod
    async def check_and_block_spam(message):
        # コマンドはスパム検知対象外（bypassロールもここで除外）
        if hasattr(message, 'content') and message.content.startswith('#'):
            from index import isCommand
            cmd_name = message.content[1:].split()[0]
            if isCommand(cmd_name):
                return False
        if MiniAntiBypass.should_bypass(message):
            return False
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        # 直近の履歴で同じ内容・タイムスタンプが近すぎる場合のみ厳しく判定
        history = user_recent_messages.get(user_id, [])
        for old_msg in history:
            # old_msgを(str, float)のタプルにして内容とタイムスタンプ両方で判定
            if isinstance(old_msg, tuple):
                old_content, old_time = old_msg
            else:
                old_content, old_time = old_msg, 0
            ratio = difflib.SequenceMatcher(None, old_content, message.content).ratio()
            # 2秒以内の連投かつ高類似度のみ厳しく
            if ratio >= SIMILARITY_THRESHOLD and abs(now - old_time) < 2:
                user_blocked_until[user_id] = now + BLOCK_DURATION
                user_recent_messages[user_id] = []
                try:
                    if hasattr(message.author, 'timed_out_until'):
                        until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                        await message.author.timeout(until, reason="miniAnti: 類似スパム検出")
                    notifier = Notifier(message)
                    await notifier.purge_user_messages(alert_type="text")
                except Exception:
                    pass
                return True
        # 履歴に(内容,タイムスタンプ)で保存
        history.append((message.content, now))
        if len(history) > RECENT_MSG_COUNT:
            history = history[-RECENT_MSG_COUNT:]
        user_recent_messages[user_id] = history

        # ランダム・意味不明スパム検知
        if hasattr(message, 'content') and is_random_spam(message.content):
            user_id = message.author.id
            now = asyncio.get_event_loop().time()
            user_blocked_until[user_id] = now + BLOCK_DURATION
            user_recent_messages[user_id] = []
            try:
                if hasattr(message.author, 'timed_out_until'):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(until, reason="miniAnti: ランダムスパム検出")
                notifier = Notifier(message)
                await notifier.purge_user_messages(alert_type="randomspam")
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
        # 画像・動画拡張子
        media_exts = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".mp4", ".mov", ".avi", ".wmv", ".webm", ".mkv")
        media_count = 0
        for att in message.attachments:
            if any(att.filename.lower().endswith(ext) for ext in media_exts):
                media_count += 1
        if media_count == 0:
            return False
        # 画像・動画共通のスパム判定
        timestamps = user_image_timestamps.get(user_id, [])
        timestamps = [t for t in timestamps if now - t < IMAGE_SPAM_WINDOW]
        timestamps.extend([now] * media_count)
        user_image_timestamps[user_id] = timestamps
        if len(timestamps) >= IMAGE_SPAM_THRESHOLD:
            user_blocked_until[user_id] = now + BLOCK_DURATION
            user_recent_messages[user_id] = []
            user_image_timestamps[user_id] = []
            try:
                if hasattr(message.author, 'timed_out_until'):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(until, reason="miniAnti: メディアスパム検出")
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
                if hasattr(message.author, 'timed_out_until'):
                    until = discord.utils.utcnow() + timedelta(seconds=BLOCK_DURATION)
                    await message.author.timeout(until, reason="miniAnti: メンションスパム検出")
                notifier = Notifier(message)
                await notifier.purge_user_messages(alert_type="mention")
            except Exception:
                pass
            return True
        return False

    @staticmethod
    async def is_user_blocked(message):
        if MiniAntiBypass.should_bypass(message):
            return False
        user_id = message.author.id
        now = asyncio.get_event_loop().time()
        # タイムアウト中かどうかも判定
        if user_id in user_blocked_until and now < user_blocked_until[user_id]:
            # すでにタイムアウト中なら何もしない
            if hasattr(message.author, 'timed_out_until') and message.author.timed_out_until:
                return True
            # まだタイムアウトが付与されていなければ付与
            try:
                until = discord.utils.utcnow() + timedelta(seconds=int(user_blocked_until[user_id] - now))
                await message.author.timeout(until, reason="miniAnti: スパム/荒らし検知による自動タイムアウト")
            except Exception:
                pass
            return True
        return False

    @staticmethod
    async def handle_griefing(message, alert_type="text"):
        # blockword系のアラートDM送信は不要なので何もしない
        if alert_type == "blockword":
            return
        notifier = Notifier(message)
        await notifier.purge_user_messages(alert_type=alert_type)

def setup(bot):
    @bot.listen('on_message')
    async def miniAnti_on_message(message):
        if message.author.bot or not message.guild:
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
        # テキストスパム判定（類似性）
        blocked = await MiniAnti.check_and_block_spam(message)
        if blocked:
            await MiniAnti.handle_griefing(message, alert_type="text")
            try:
                await message.delete()
            except:
                pass
            return

    @bot.command()
    async def minianti(ctx, subcmd: str = "", arg: str = ""):
        """
        miniAntiの設定・管理コマンド
        #minianti settings: 現在の設定をEmbedで表示
        #minianti docs: 各種機能の説明をEmbedで表示
        #minianti bypass <roleID>: 指定ロールをbypass（スパム判定除外）に設定（管理者のみ）
        #minianti unblock <ユーザーID>: 指定ユーザーのblock/タイムアウトを解除（管理者のみ）
        #minianti block <ユーザーID> <期間>: 指定ユーザーを任意期間ブロック（例: 1m, 2h, 3d, 10s）（管理者のみ）
        #minianti list: 現在ブロック中のユーザー一覧を表示
        (設定変更機能は今後も実装しません)
        """
        if subcmd.lower() == "bypass":
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
                await ctx.send("ロールIDを指定してください。例: #minianti bypass 123456789012345678", delete_after=10)
                return
            role_id = int(arg)
            role = ctx.guild.get_role(role_id)
            if not role:
                await ctx.send("指定したロールが見つかりません。", delete_after=10)
                return
            update_guild_data(ctx.guild.id, "miniAntiBypassRole", role_id)
            await ctx.send(f"✅ このサーバーのminiAnti bypassロールを `{role.name}` (ID: {role_id}) に設定しました。", delete_after=10)
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
                await ctx.send("ユーザーIDを指定してください。例: #minianti unblock 123456789012345678", delete_after=10)
                return
            user_id = int(arg)
            member = ctx.guild.get_member(user_id)
            # miniAntiの内部block解除
            global user_blocked_until
            if user_id in user_blocked_until:
                del user_blocked_until[user_id]
            # Discordのタイムアウト解除
            if member:
                try:
                    await member.edit(timed_out_until=None, reason="miniAnti: 管理者による手動unblock")
                except Exception:
                    pass
            await ctx.send(f"✅ ユーザーID `{user_id}` のblock/タイムアウトを解除しました。", delete_after=10)
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
                await ctx.send("ユーザーIDと期間を指定してください。例: #minianti block 123456789012345678 1m", delete_after=10)
                return
            user_id = int(args[0])
            duration_str = args[1]
            import re
            m = re.match(r"(\d+)([smhd])", duration_str)
            if not m:
                await ctx.send("期間の形式が不正です。例: 1m, 2h, 3d, 10s", delete_after=10)
                return
            num, unit = int(m.group(1)), m.group(2)
            seconds = num * {"s":1, "m":60, "h":3600, "d":86400}[unit]
            global user_blocked_until
            now = asyncio.get_event_loop().time()
            user_blocked_until[user_id] = now + seconds
            member = ctx.guild.get_member(user_id)
            if member:
                try:
                    until = discord.utils.utcnow() + timedelta(seconds=seconds)
                    await member.timeout(until, reason="miniAnti: 管理者による手動block")
                except Exception:
                    pass
            await ctx.send(f"✅ ユーザーID `{user_id}` を {duration_str} ブロックしました。", delete_after=10)
            return
        if subcmd.lower() == "list":
            now = asyncio.get_event_loop().time()
            blocked = [(uid, until) for uid, until in user_blocked_until.items() if until > now]
            if not blocked:
                await ctx.send("現在ブロック中のユーザーはいません。", delete_after=10)
                return
            embed = discord.Embed(title="miniAnti ブロック中ユーザー一覧", color=0xA21CAF)
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
                embed.add_field(name=f"ユーザーID: {uid}", value=f"残り: {time_str}", inline=False)
            await ctx.send(embed=embed)
            return
        if not subcmd:
            await ctx.send("`#minianti docs` を指定してください。", delete_after=10)
            return
        elif subcmd.lower() == "docs":
            embed = discord.Embed(
                title="miniAnti 機能説明",
                color=0x38bdf8
            )
            embed.add_field(
                name="テキストスパム検知",
                value="直近のメッセージ履歴と類似度でスパムを自動検知・タイムアウトします。",
                inline=False
            )
            embed.add_field(
                name="画像・動画スパム検知",
                value="短時間に画像や動画を連投した場合に自動でタイムアウトします。",
                inline=False
            )
            embed.add_field(
                name="メンションスパム検知",
                value="短時間に複数人へメンションを連投した場合に自動でタイムアウトします。",
                inline=False
            )
            embed.add_field(
                name="自動タイムアウト・削除",
                value="スパム検知時は自動でタイムアウト・メッセージ削除・DM警告を行います。",
                inline=False
            )
            embed.set_footer(text="miniAnti v1.0 | どなたでも閲覧可能です。詳細は管理者まで")
            await ctx.send(embed=embed)
        else:
            await ctx.send("`docs` を指定してください。", delete_after=10)

