# AntiCheat統合設定管理
import json
from typing import Optional, Dict, Any

class AntiCheatConfig:
    """
    AntiCheat機能の統合設定管理クラス
    """
    
    DEFAULT_CONFIG = {
        "alert_channel": None,
        "bypass_role": None,
        "enabled": False,
        "detection_settings": {
            "text_spam": True,
            "image_spam": True,
            "mention_spam": True,
            "token_spam": True,
            "timebase_spam": True,
            "typing_bypass": True,
            "forward_spam": True,  
        }
    }
    
    @staticmethod
    async def get_config(guild) -> Dict[str, Any]:
        """
        ギルドのAntiCheat設定を取得
        """
        try:
            from . import GuildConfig
            config = await GuildConfig.load_guild_json(guild, "AntiCheat")
            if not config:
                return AntiCheatConfig.DEFAULT_CONFIG.copy()
            
            # デフォルト設定とマージ（新しい設定項目の追加に対応）
            merged_config = AntiCheatConfig.DEFAULT_CONFIG.copy()
            AntiCheatConfig._deep_merge(merged_config, config)
            return merged_config
        except Exception as e:
            print(f"[AntiCheat] Failed to load config: {e}")
            return AntiCheatConfig.DEFAULT_CONFIG.copy()
    
    @staticmethod
    async def save_config(guild, config: Dict[str, Any]):
        """
        ギルドのAntiCheat設定を保存
        """
        try:
            from . import GuildConfig
            await GuildConfig.save_guild_json(guild, "AntiCheat", config)
            print(f"[AntiCheat] Config saved for guild {guild.name}")
        except Exception as e:
            print(f"[AntiCheat] Failed to save config: {e}")
    
    @staticmethod
    async def update_setting(guild, key_path: str, value: Any):
        """
        特定の設定項目を更新
        key_path例: "alert_channel", "detection_settings.text_spam", "thresholds.mention_limit"
        """
        config = await AntiCheatConfig.get_config(guild)
        AntiCheatConfig._set_nested_value(config, key_path, value)
        await AntiCheatConfig.save_config(guild, config)
    
    @staticmethod
    async def get_setting(guild, key_path: str, default=None):
        """
        特定の設定項目を取得
        """
        config = await AntiCheatConfig.get_config(guild)
        return AntiCheatConfig._get_nested_value(config, key_path, default)
    
    @staticmethod
    def _deep_merge(base_dict: Dict, update_dict: Dict):
        """
        辞書の深いマージ
        """
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                AntiCheatConfig._deep_merge(base_dict[key], value)
            else:
                base_dict[key] = value
    
    @staticmethod
    def _get_nested_value(config: Dict, key_path: str, default=None):
        """
        ネストされた設定値を取得
        """
        keys = key_path.split('.')
        current = config
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current
    
    @staticmethod
    def _set_nested_value(config: Dict, key_path: str, value: Any):
        """
        ネストされた設定値を設定
        """
        keys = key_path.split('.')
        current = config
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        current[keys[-1]] = value
    
    @staticmethod
    async def is_enabled(guild) -> bool:
        """
        AntiCheat機能が有効かチェック
        """
        result = await AntiCheatConfig.get_setting(guild, "enabled", True)
        return bool(result)
    
    @staticmethod
    async def is_detection_enabled(guild, detection_type: str) -> bool:
        """
        特定の検知機能が有効かチェック
        """
        result = await AntiCheatConfig.get_setting(guild, f"detection_settings.{detection_type}", True)
        return bool(result)
