# バイパス判定（MiniAntiBypass）
class MiniAntiBypass:
    @staticmethod
    async def should_bypass(message):
        """
        指定されたメッセージの送信者がバイパス権限を持っているかチェック
        """
        if not message.guild:
            return False
        
        try:
            # AntiCheatConfigを使用してバイパスロールIDを取得
            from .config import AntiCheatConfig
            bypass_role_id = await AntiCheatConfig.get_setting(message.guild, "bypass_role")
            
            if not bypass_role_id:
                return False
            
            # ロールIDを整数に変換
            try:
                if bypass_role_id is not None and str(bypass_role_id).isdigit():
                    bypass_role_id = int(str(bypass_role_id))
                else:
                    return False
            except (ValueError, TypeError):
                print(f"[miniAnti] Invalid bypass role ID: {bypass_role_id}")
                return False
            
            # ユーザーが該当ロールを持っているかチェック
            if hasattr(message.author, "roles"):
                for role in message.author.roles:
                    if role.id == bypass_role_id:
                        #print(f"[miniAnti] Bypass granted for user {message.author} (role: {role.name})")
                        return True
            
            return False
            
        except Exception as e:
            print(f"[miniAnti] Error in bypass check: {e}")
            return False
    
    @staticmethod
    def should_bypass_sync(message):
        """
        同期版のバイパスチェック（後方互換性のため）
        注意: この関数は非推奨です。should_bypass()を使用してください。
        """
        if not message.guild:
            return False
        
        try:
            from DataBase import get_guild_value
            bypass_role_id = get_guild_value(message.guild.id, "miniAntiBypassRole")
            if bypass_role_id:
                try:
                    bypass_role_id = int(bypass_role_id)
                except Exception:
                    return False
                if any(
                    getattr(r, "id", None) == bypass_role_id
                    for r in getattr(message.author, "roles", [])
                ):
                    return True
            return False
        except Exception:
            return False

