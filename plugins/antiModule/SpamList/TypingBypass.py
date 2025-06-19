import time
from typing import Any, Callable


class TypingBypass:
    typing_timestamps = {}
    _bot: Any = None
    _on_typing_handler = None
    TYPING_BYPASS_WINDOW = 300
    @classmethod
    def set_bot(cls, bot: Any):
        cls._bot = bot
        if bot is not None:
            try:
                from index import registerBotEvent, unregisterBotEvent

                async def on_typing(channel, user, when):
                    await cls.record_typing_start(user.id)

                if cls._on_typing_handler:
                    unregisterBotEvent(bot, "on_typing", cls._on_typing_handler)
                registerBotEvent(bot, "on_typing", on_typing)
                cls._on_typing_handler = on_typing
            except Exception as e:
                print(f"[TypingBypass] registerBotEvent の登録に失敗: {e}")

    @staticmethod
    async def record_typing_start(user_id: int):
        now = time.time()
        TypingBypass.typing_timestamps[user_id] = now

    @staticmethod
    async def check_and_block_typing_bypass(message: Any) -> bool:
        user_id = message.author.id
        current_time = time.time()
        content = getattr(message, 'content', '')
        # 10文字以下のメッセージは許可
        if len(content) <= 10:
            return False
        if user_id not in TypingBypass.typing_timestamps:
            try:
                await message.delete()
            except Exception as e:
                print(f"[TypingBypass] message.delete error: {e}")
            return False
        last_typing = TypingBypass.typing_timestamps.get(user_id)
        if last_typing is not None and current_time - last_typing <= TypingBypass.TYPING_BYPASS_WINDOW:
            return False
        print(f"Typing Bypass detected: {message.author.name} in {message.channel.id}")
        try:
            from plugins.antiModule.SpamList.TextSpam import TextSpam
            from plugins.antiModule.spam import _now, DEFAULT_TIMEOUT_DURATION
            uid = user_id
            now = _now()
            alert_type = "typing_bypass"
            timeout_duration = DEFAULT_TIMEOUT_DURATION
            reason = "Typing Bypass検知による自動タイムアウト"
            await TextSpam.block_and_notify(
                message,
                uid,
                now,
                alert_type,
                timeout_duration,
                reason
            )
        except Exception as e:
            print(f"[TypingBypass] block_and_notify error: {e}")
        return True
