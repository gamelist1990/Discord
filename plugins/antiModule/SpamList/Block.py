from plugins.antiModule.spam import user_blocked_until, _now

class Block:
    @staticmethod
    async def is_user_blocked(message):
        uid = message.author.id
        now = _now()
        if uid in user_blocked_until and user_blocked_until[uid] > now:
            return True
        return False
