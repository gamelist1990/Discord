from plugins.antiModule.commands import setup_anti_commands
from plugins.antiModule.spam import Block, Griefing
from plugins.antiModule.SpamList.TextSpam import TextSpam
from plugins.antiModule.SpamList.MediaSpam import MediaSpam
from plugins.antiModule.SpamList.MentionSpam import MentionSpam
from plugins.antiModule.SpamList.TokenSpam import TokenSpam
from plugins.antiModule.SpamList.TimebaseSpam import TimebaseSpam
from plugins.antiModule.SpamList.TypingBypass import TypingBypass
from plugins.antiModule.SpamList.ForwardSpam import ForwardSpam
from plugins.antiModule.flag_system import FlagSystem
from discord.ext.commands import Bot
from discord import Message


def setup(bot: Bot):
    TypingBypass.set_bot(bot)
    
    @bot.listen("on_message")
    async def miniAnti_on_message(message: Message):
        if message.author.bot or not message.guild:
            return
        print(f"miniAnti: {message.channel.id} {message.content} {message.author.name}")

        # Token/Webhookスパム判定（最優先）
        token_blocked = await TokenSpam.check_and_block_token_spam(message)
        if token_blocked:
            await Griefing.handle_griefing(message, alert_type="token")
            try:
                await message.delete()
            except:
                pass
            return
        
        # ブロック中なら削除
        if await Block.is_user_blocked(message):
            try:
                await message.delete()
            except:
                pass
            return
        
        # 画像・動画スパム判定
        media_blocked = await MediaSpam.check_and_block_media_spam(message)
        if media_blocked:
            await Griefing.handle_griefing(message, alert_type="image")
            try:
                await message.delete()
            except:
                pass
            return
        
        # メンションスパム判定
        mention_blocked = await MentionSpam.check_and_block_mention_spam(message)
        if mention_blocked:
            await Griefing.handle_griefing(message, alert_type="mention")
            try:
                await message.delete()
            except:
                pass
            return
        
        # タイムベース検知
        timebase_blocked = await TimebaseSpam.check_and_block_timebase_spam(message)
        if timebase_blocked:
            await Griefing.handle_griefing(message, alert_type="timebase")
            try:
                await message.delete()
            except:
                pass
            return
        
        # Typing Bypass 検知
        typing_bypass_blocked = await TypingBypass.check_and_block_typing_bypass(message)
        if typing_bypass_blocked:
            await Griefing.handle_griefing(message, alert_type="typing_bypass")
            try:
                await message.delete()
            except:
                pass
            return
        
        # 転送スパム判定
        forward_blocked = await ForwardSpam.check_and_block_forward_spam(message)
        if forward_blocked:
            await Griefing.handle_griefing(message, alert_type="forward")
            try:
                await message.delete()
            except:
                pass
            return
        
        # テキストスパム判定
        blocked = await TextSpam.check_and_block_spam(message)
        if blocked:
            await Griefing.handle_griefing(message, alert_type="text")
            try:
                await message.delete()
            except:
                pass
            return

    setup_anti_commands(bot)
