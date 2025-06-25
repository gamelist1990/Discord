import aiohttp
from typing import Optional, Dict, Any, Union


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


class WebDiscordAPIv9:
    """
    Discord v9 API（BotToken不要）用ユーティリティ。
    v9でのみ利用可能・v10では廃止されたエンドポイント中心。
    """

    BASE_URL = "https://discord.com/api/v9"
    USER_AGENT = "Mozilla/5.0"

    # --- 招待系 ---
    @staticmethod
    async def get_invite_info(invite_code, timeout=5) -> Union[DiscordInviteInfo, None]:
        """招待コード情報取得（v9版）"""
        url = f"{WebDiscordAPIv9.BASE_URL}/invites/{invite_code}?with_counts=true&with_expiration=true"
        headers = {"User-Agent": WebDiscordAPIv9.USER_AGENT}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return DiscordInviteInfo(data)
        except Exception:
            pass
        return None

    # --- アプリケーション・ゲーム系 ---
    @staticmethod
    async def get_detectable_applications(timeout=5) -> Optional[Dict[str, Any]]:
        """検出可能なアプリケーション一覧"""
        url = f"{WebDiscordAPIv9.BASE_URL}/applications/detectable"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    async def get_application_public(
        application_id, timeout=5
    ) -> Optional[Dict[str, Any]]:
        """パブリックアプリケーション情報"""
        url = f"{WebDiscordAPIv9.BASE_URL}/applications/{application_id}/public"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    # --- ユーザー系 ---
    @staticmethod
    async def get_user_profile(user_id, timeout=5) -> Optional[Dict[str, Any]]:
        """ユーザープロフィール（v9版）"""
        url = f"{WebDiscordAPIv9.BASE_URL}/users/{user_id}/profile"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    # --- ギルド系（v9独自） ---
    @staticmethod
    async def get_guild_widget_v9(guild_id, timeout=5) -> Optional[Dict[str, Any]]:
        """ギルドウィジェット（v9版）"""
        url = f"{WebDiscordAPIv9.BASE_URL}/guilds/{guild_id}/widget.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    # --- 実験・機能系 ---
    @staticmethod
    async def get_experiments(timeout=5) -> Optional[Dict[str, Any]]:
        """実験機能一覧"""
        url = f"{WebDiscordAPIv9.BASE_URL}/experiments"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    # --- スタンプ系 ---
    @staticmethod
    async def get_sticker_packs(timeout=5) -> Optional[Dict[str, Any]]:
        """スタンプパック一覧（v9版）"""
        url = f"{WebDiscordAPIv9.BASE_URL}/sticker-packs"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None

    @staticmethod
    async def get_sticker_pack_by_id(pack_id, timeout=5) -> Optional[Dict[str, Any]]:
        """特定スタンプパック詳細"""
        url = f"{WebDiscordAPIv9.BASE_URL}/sticker-packs/{pack_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return None


class WebDiscordAPIv10:
    """
    Discord v10 API（BotToken不要）用ユーティリティ。
    v10で拡張・安定化されたエンドポイント中心。
    """

    BASE_URL = "https://discord.com/api/v10"
    USER_AGENT = "Mozilla/5.0"

    # --- 招待系 ---
    @staticmethod
    async def get_invite_info(
        invite_code, timeout=5
    ) -> Union[DiscordInviteInfo, Dict[str, str], None]:
        """招待コード情報取得（v10版）"""
        url = f"{WebDiscordAPIv10.BASE_URL}/invites/{invite_code}?with_counts=true&with_expiration=true"
        headers = {"User-Agent": WebDiscordAPIv10.USER_AGENT}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return DiscordInviteInfo(data)
                    elif resp.status == 404:
                        return {"error": "Not Found", "reason": "Invalid invite code."}
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- ギルド系（完全版） ---
    @staticmethod
    async def get_guild_preview(guild_id, timeout=5) -> Optional[Dict[str, Any]]:
        """ギルドプレビュー（公開サーバーのみ）"""
        url = f"{WebDiscordAPIv10.BASE_URL}/guilds/{guild_id}/preview"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 401:
                        return {
                            "error": "Unauthorized",
                            "reason": "This guild is not public or preview is not available.",
                        }
                    elif resp.status == 404:
                        return {
                            "error": "Not Found",
                            "reason": "Guild not found or preview not available.",
                        }
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_guild_discovery_metadata(
        guild_id, timeout=5
    ) -> Optional[Dict[str, Any]]:
        """ギルドディスカバリーメタデータ（公開サーバーのみ）"""
        url = f"{WebDiscordAPIv10.BASE_URL}/guilds/{guild_id}/discovery-metadata"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 403:
                        return {
                            "error": "Forbidden",
                            "reason": "Guild discovery is not enabled.",
                        }
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_guild_widget(guild_id, timeout=5) -> Optional[Dict[str, Any]]:
        """ギルドウィジェット情報"""
        url = f"https://discord.com/api/guilds/{guild_id}/widget.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 403:
                        return {
                            "error": "Forbidden",
                            "reason": "Widget is disabled for this guild.",
                        }
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_guild_vanity_url(guild_id, timeout=5) -> Optional[Dict[str, Any]]:
        """ギルドバニティURL"""
        url = f"{WebDiscordAPIv10.BASE_URL}/guilds/{guild_id}/vanity-url"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 404:
                        return {
                            "error": "Not Found",
                            "reason": "Guild does not have a vanity URL.",
                        }
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_discoverable_guilds(timeout=5) -> Optional[Dict[str, Any]]:
        """発見可能ギルド一覧"""
        url = f"{WebDiscordAPIv10.BASE_URL}/discoverable-guilds"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- アプリケーション系 ---
    @staticmethod
    async def get_application_public(
        application_id, timeout=5
    ) -> Optional[Dict[str, Any]]:
        """パブリックアプリケーション情報（v10版）"""
        url = f"{WebDiscordAPIv10.BASE_URL}/applications/{application_id}/public"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_application_directory_categories(
        timeout=5,
    ) -> Optional[Dict[str, Any]]:
        """アプリケーションディレクトリカテゴリ"""
        url = f"{WebDiscordAPIv10.BASE_URL}/application-directory/categories"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_application_directory_recommended(
        timeout=5,
    ) -> Optional[Dict[str, Any]]:
        """推奨アプリケーション"""
        url = f"{WebDiscordAPIv10.BASE_URL}/application-directory/applications/recommended"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- ユーザー系 ---
    @staticmethod
    async def get_user_info(user_id, timeout=5) -> Optional[Dict[str, Any]]:
        """ユーザー情報"""
        url = f"{WebDiscordAPIv10.BASE_URL}/users/{user_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 404:
                        return {"error": "Not Found", "reason": "User not found."}
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_user_profile(user_id, timeout=5) -> Optional[Dict[str, Any]]:
        """ユーザープロフィール（v10版）"""
        url = f"{WebDiscordAPIv10.BASE_URL}/users/{user_id}/profile"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- ゲートウェイ系 ---
    @staticmethod
    async def get_gateway(timeout=5) -> Optional[Dict[str, Any]]:
        """ゲートウェイ情報"""
        url = f"{WebDiscordAPIv10.BASE_URL}/gateway"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- Voice系 ---
    @staticmethod
    async def get_voice_regions(timeout=5) -> Optional[Dict[str, Any]]:
        """ボイス地域一覧"""
        url = f"{WebDiscordAPIv10.BASE_URL}/voice/regions"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- GIF・スタンプ系 ---
    @staticmethod
    async def get_trending_gifs(timeout=5) -> Optional[Dict[str, Any]]:
        """トレンドGIF一覧"""
        url = f"{WebDiscordAPIv10.BASE_URL}/gifs/trending"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_gif_suggestions(query, timeout=5) -> Optional[Dict[str, Any]]:
        """GIF検索候補"""
        url = f"{WebDiscordAPIv10.BASE_URL}/gifs/suggest?q={query}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_sticker_packs(timeout=5) -> Optional[Dict[str, Any]]:
        """スタンプパック一覧（v10版）"""
        url = f"{WebDiscordAPIv10.BASE_URL}/sticker-packs"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    @staticmethod
    async def get_sticker_pack_by_id(pack_id, timeout=5) -> Optional[Dict[str, Any]]:
        """特定スタンプパック詳細（v10版）"""
        url = f"{WebDiscordAPIv10.BASE_URL}/sticker-packs/{pack_id}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- 外部ステータス系 ---
    @staticmethod
    async def get_discord_status(timeout=5) -> Optional[Dict[str, Any]]:
        """Discord全体稼働状況"""
        url = "https://discordstatus.com/api/v2/status.json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            return {"error": "Exception", "reason": str(e)}
        return None

    # --- 画像URL生成系 ---
    @staticmethod
    def get_guild_widget_image(guild_id) -> str:
        """ギルドウィジェット画像URL"""
        return f"https://discord.com/api/guilds/{guild_id}/widget.png"

    @staticmethod
    def get_guild_banner(guild_id, banner_hash) -> Optional[str]:
        """ギルドバナー画像URL"""
        if not banner_hash:
            return None
        return f"https://cdn.discordapp.com/banners/{guild_id}/{banner_hash}.png"

    @staticmethod
    def get_guild_icon(guild_id, icon_hash) -> Optional[str]:
        """ギルドアイコン画像URL"""
        if not icon_hash:
            return None
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png"

    @staticmethod
    def get_user_avatar(user_id, avatar_hash) -> Optional[str]:
        """ユーザーアバター画像URL"""
        if not avatar_hash:
            return None
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"

    @staticmethod
    def get_user_default_avatar(discriminator) -> str:
        """デフォルトアバター画像URL"""
        return f"https://cdn.discordapp.com/embed/avatars/{int(discriminator) % 5}.png"

    @staticmethod
    def get_application_icon(application_id, icon_hash) -> Optional[str]:
        """アプリケーションアイコン画像URL"""
        if not icon_hash:
            return None
        return f"https://cdn.discordapp.com/app-icons/{application_id}/{icon_hash}.png"


# --- 統合ユーティリティクラス ---
class WebDiscordAPI:
    """
    v9/v10両方を統合した便利クラス。
    """

    v9 = WebDiscordAPIv9
    v10 = WebDiscordAPIv10

    @staticmethod
    async def get_invite_info_both(invite_code, timeout=5):
        """v9・v10両方で招待情報を取得・比較"""
        v9_result = await WebDiscordAPIv9.get_invite_info(invite_code, timeout)
        v10_result = await WebDiscordAPIv10.get_invite_info(invite_code, timeout)
        return {"v9": v9_result, "v10": v10_result}

    @staticmethod
    async def get_sticker_packs_both(timeout=5):
        """v9・v10両方でスタンプパック一覧を取得・比較"""
        v9_result = await WebDiscordAPIv9.get_sticker_packs(timeout)
        v10_result = await WebDiscordAPIv10.get_sticker_packs(timeout)
        return {"v9": v9_result, "v10": v10_result}


if __name__ == "__main__":
    import asyncio

    async def main():
        guild_id = "890315487962095637"
        invite_code = "ZshgGwFQ"

        print("=== v9 APIs ===")
        print("--- v9 get_invite_info ---")
        invite_v9 = await WebDiscordAPIv9.get_invite_info(invite_code)
        if isinstance(invite_v9, DiscordInviteInfo):
            print("成功:", vars(invite_v9))
        else:
            print("結果:", invite_v9)

        print("--- v9 get_detectable_applications ---")
        apps_v9 = await WebDiscordAPIv9.get_detectable_applications()
        print("結果:", "成功" if apps_v9 else "失敗/None")

        print("--- v9 get_experiments ---")
        exp_v9 = await WebDiscordAPIv9.get_experiments()
        print("結果:", "成功" if exp_v9 else "失敗/None")

        print("\n=== v10 APIs ===")
        print("--- v10 get_invite_info ---")
        invite_v10 = await WebDiscordAPIv10.get_invite_info(invite_code)
        if isinstance(invite_v10, DiscordInviteInfo):
            print("成功:", vars(invite_v10))
        else:
            print("結果:", invite_v10)

        print("--- v10 get_guild_preview ---")
        preview = await WebDiscordAPIv10.get_guild_preview(guild_id)
        print("結果:", preview)

        print("--- v10 get_discoverable_guilds ---")
        discover = await WebDiscordAPIv10.get_discoverable_guilds()
        print("結果:", "成功" if discover else "失敗/None")

        print("--- v10 get_trending_gifs ---")
        gifs = await WebDiscordAPIv10.get_trending_gifs()
        print("結果:", "成功" if gifs else "失敗/None")

        print("--- v10 get_gateway ---")
        gateway = await WebDiscordAPIv10.get_gateway()
        print("結果:", gateway)

        print("--- v10 get_voice_regions ---")
        regions = await WebDiscordAPIv10.get_voice_regions()
        print("結果:", "成功" if regions else "失敗/None")

        print("\n=== 統合比較 ===")
        print("--- 招待情報v9 vs v10 ---")
        both_invites = await WebDiscordAPI.get_invite_info_both(invite_code)
        print(
            "v9結果:",
            (
                "成功"
                if isinstance(both_invites["v9"], DiscordInviteInfo)
                else both_invites["v9"]
            ),
        )
        print(
            "v10結果:",
            (
                "成功"
                if isinstance(both_invites["v10"], DiscordInviteInfo)
                else both_invites["v10"]
            ),
        )

    try:
        asyncio.run(main())
    except Exception as e:
        print({"error": "Exception", "reason": str(e)})
