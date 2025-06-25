import aiohttp
from typing import Optional

class DiscordInviteInfo:
    def __init__(self, data: dict):
        self.type = data.get("type")
        self.code = data.get("code")
        self.guild = data.get("guild", {})
        self.guild_id = data.get("guild_id")
        self.guild_name = self.guild.get("name", "")
        self.guild_description = self.guild.get("description", "")
        self.profile = data.get("profile", {})
        self.profile_name = self.profile.get("name", "")
        self.profile_description = self.profile.get("description", "")
        self.channel = data.get("channel", {})
        self.inviter = data.get("inviter", {})
        # 必要に応じて他のフィールドも追加

class WebDiscordAPI:
    """
    DiscordのBotToken不要で利用できる主なWeb APIユーティリティ集。
    """
    BASE_URL = "https://discord.com/api/v10"
    USER_AGENT = "Mozilla/5.0"

    # --- 招待・サーバー・ユーザー・画像系 ---
    @staticmethod
    async def get_invite_info(invite_code, timeout=5) -> Optional[DiscordInviteInfo]:
        """
        Discord招待コードからサーバー・チャンネル・招待者などの情報を取得。
        """
        url = f"{WebDiscordAPI.BASE_URL}/invites/{invite_code}?with_counts=false&with_expiration=false"
        headers = {"User-Agent": WebDiscordAPI.USER_AGENT}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return DiscordInviteInfo(data)
        except Exception:
            pass
        return None

    @staticmethod
    def get_discord_guild_widget_image(guild_id) -> str:
        """
        サーバーのウィジェット画像URLを取得（ウィジェット有効時のみ）。
        """
        return f"https://discord.com/api/guilds/{guild_id}/widget.png"

    @staticmethod
    def get_discord_guild_banner(guild_id, banner_hash) -> Optional[str]:
        """
        サーバーのバナー画像URLを生成（バナーが設定されている場合）。
        """
        if not banner_hash:
            return None
        return f"https://cdn.discordapp.com/banners/{guild_id}/{banner_hash}.png"

    @staticmethod
    def get_discord_guild_icon(guild_id, icon_hash) -> Optional[str]:
        """
        サーバーのアイコン画像URLを生成（アイコンが設定されている場合）。
        """
        if not icon_hash:
            return None
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png"

    @staticmethod
    def get_discord_user_avatar(user_id, avatar_hash) -> Optional[str]:
        """
        ユーザーのアバター画像URLを生成（アバターが設定されている場合）。
        """
        if not avatar_hash:
            return None
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"

    # --- サーバー・ウィジェット・バニティ・プレビュー・ディスカバリー ---
    @staticmethod
    async def get_discord_guild_widget(guild_id, timeout=5) -> Optional[dict]:
        """
        サーバーのウィジェット情報（オンライン人数・チャンネル名・一部メンバー名など）を取得。
        サーバー側でウィジェット有効時のみ。
        """
        url = f"https://discord.com/api/guilds/{guild_id}/widget.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    async def get_discord_guild_vanity_url(guild_id, timeout=5) -> Optional[dict]:
        """
        サーバーのバニティURL（カスタム招待コード）情報を取得。
        ※サーバーがバニティURLを設定している場合のみ有効。
        """
        url = f"https://discord.com/api/v10/guilds/{guild_id}/vanity-url"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    async def get_guild_preview(guild_id, timeout=5) -> Optional[dict]:
        """
        サーバーのプレビュー情報（公開サーバーのみ、メンバー数・説明・アイコン等）を取得。
        公開サーバーでない場合やアクセス不可時はエラー情報を返す。
        """
        url = f"https://discord.com/api/v10/guilds/{guild_id}/preview"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 401:
                        return {"error": "Unauthorized", "reason": "This guild is not public or preview is not available."}
                    elif resp.status == 404:
                        return {"error": "Not Found", "reason": "Guild not found or preview not available."}
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_guild_discovery_metadata(guild_id, timeout=5) -> Optional[dict]:
        """
        サーバーのディスカバリーメタデータ（公開サーバーのみ）を取得。
        """
        url = f"https://discord.com/api/v10/guilds/{guild_id}/discovery-metadata"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    # --- ステータス・スタンプ・GIF ---
    @staticmethod
    async def get_discord_status(timeout=5) -> Optional[dict]:
        """
        Discord全体の稼働状況（API/メディア/ゲートウェイ等）を取得。
        """
        url = "https://discordstatus.com/api/v2/status.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    async def get_sticker_packs(timeout=5) -> Optional[dict]:
        """
        スタンプパック一覧を取得。
        """
        url = "https://discord.com/api/v10/sticker-packs"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    async def get_trending_gifs(timeout=5) -> Optional[dict]:
        """
        トレンドGIF一覧を取得。
        """
        url = "https://discord.com/api/v10/gifs/trending"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

if __name__ == "__main__":
    import asyncio

    async def main():
        guild_id = "890315487962095637"
        invite_code = "ZshgGwFQ"
        print("--- get_guild_preview ---")
        preview = await WebDiscordAPI.get_guild_preview(guild_id)
        print(preview)
        print("--- get_invite_info ---")
        invite = await WebDiscordAPI.get_invite_info(invite_code)
        if isinstance(invite, DiscordInviteInfo):
            print(vars(invite))
        else:
            print(invite)

    try:
        asyncio.run(main())
    except Exception as e:
        print({"error": "Exception", "reason": str(e)})
