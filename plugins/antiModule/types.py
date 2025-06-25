# AntiModuleの検知タイプ定義
from typing import Dict, NamedTuple


class DetectionType:
    """検知タイプの定数定義"""
    
    # 基本検知タイプ
    TEXT = "text"
    IMAGE = "image"
    MENTION = "mention"
    TOKEN = "token"
    TIMEBASE = "timebase"
    TYPING_BYPASS = "typing_bypass"
    FORWARD = "forward"
    
    # 大人数スパム用
    MASS_TEXT = "mass_text"
    MASS_IMAGE = "mass_image"
    MASS_MENTION = "mass_mention"
    
    # 全検知タイプのリスト
    ALL_TYPES = [
        TEXT, IMAGE, MENTION, TOKEN, TIMEBASE, TYPING_BYPASS, FORWARD
    ]
    
    # 大人数検知タイプのリスト
    MASS_TYPES = [
        MASS_TEXT, MASS_IMAGE, MASS_MENTION
    ]


class DetectionInfo(NamedTuple):
    """検知タイプの詳細情報"""
    emoji: str
    name: str
    color: int
    config_key: str  # 設定での識別キー


class DetectionTypeManager:
    """検知タイプの管理クラス"""
    
    # 検知タイプ情報のマッピング
    TYPE_INFO = {
        DetectionType.TEXT: DetectionInfo(
            emoji="📝",
            name="テキストスパム",
            color=0xFF6B6B,
            config_key="text_spam"
        ),
        DetectionType.IMAGE: DetectionInfo(
            emoji="🖼️",
            name="画像スパム",
            color=0xFFB347,
            config_key="image_spam"
        ),
        DetectionType.MENTION: DetectionInfo(
            emoji="📢",
            name="メンションスパム",
            color=0x87CEEB,
            config_key="mention_spam"
        ),
        DetectionType.TOKEN: DetectionInfo(
            emoji="🚨",
            name="Tokenスパム",
            color=0x8B0000,
            config_key="token_spam"
        ),
        DetectionType.TIMEBASE: DetectionInfo(
            emoji="⏰",
            name="タイムベーススパム",
            color=0xDDA0DD,
            config_key="timebase_spam"
        ),
        DetectionType.TYPING_BYPASS: DetectionInfo(
            emoji="⌨️",
            name="Typing Bypass",
            color=0x20B2AA,
            config_key="typing_bypass"
        ),
        DetectionType.FORWARD: DetectionInfo(
            emoji="↗️",
            name="転送スパム",
            color=0x32CD32,
            config_key="forward_spam"
        ),
        # 大人数スパム用
        DetectionType.MASS_TEXT: DetectionInfo(
            emoji="🚨📝",
            name="大人数テキストスパム",
            color=0x8B0000,
            config_key="mass_text_spam"
        ),
        DetectionType.MASS_IMAGE: DetectionInfo(
            emoji="🚨🖼️",
            name="大人数画像スパム",
            color=0xFF4500,
            config_key="mass_image_spam"
        ),
        DetectionType.MASS_MENTION: DetectionInfo(
            emoji="🚨📢",
            name="大人数メンションスパム",
            color=0x4169E1,
            config_key="mass_mention_spam"
        ),
    }
    
    @classmethod
    def get_info(cls, detection_type: str) -> DetectionInfo:
        """検知タイプの情報を取得"""
        return cls.TYPE_INFO.get(detection_type, DetectionInfo("❓", "不明", 0x808080, "unknown"))
    
    @classmethod
    def get_display_name(cls, detection_type: str) -> str:
        """検知タイプの表示名を取得"""
        info = cls.get_info(detection_type)
        return f"{info.emoji} {info.name}"
    
    @classmethod
    def get_emoji(cls, detection_type: str) -> str:
        """検知タイプの絵文字を取得"""
        return cls.get_info(detection_type).emoji
    
    @classmethod
    def get_name(cls, detection_type: str) -> str:
        """検知タイプの名前を取得"""
        return cls.get_info(detection_type).name
    
    @classmethod
    def get_color(cls, detection_type: str) -> int:
        """検知タイプの色を取得"""
        return cls.get_info(detection_type).color
    
    @classmethod
    def get_config_key(cls, detection_type: str) -> str:
        """検知タイプの設定キーを取得"""
        return cls.get_info(detection_type).config_key
    
    @classmethod
    def get_all_detection_types(cls) -> Dict[str, str]:
        """全検知タイプの表示名マップを取得"""
        return {
            detection_type: cls.get_display_name(detection_type)
            for detection_type in DetectionType.ALL_TYPES
        }
    
    @classmethod
    def get_config_display_names(cls) -> Dict[str, str]:
        """設定画面用の表示名マップを取得"""
        return {
            cls.get_config_key(detection_type): cls.get_display_name(detection_type)
            for detection_type in DetectionType.ALL_TYPES
        }
    
    @classmethod
    def get_flag_weight_display_names(cls) -> Dict[str, str]:
        """フラグ重み設定用の表示名マップを取得"""
        return {
            detection_type: cls.get_display_name(detection_type)
            for detection_type in DetectionType.ALL_TYPES
        }


# 便利な関数
def get_detection_display_name(detection_type: str) -> str:
    """検知タイプの表示名を取得する便利関数"""
    return DetectionTypeManager.get_display_name(detection_type)


def get_detection_color(detection_type: str) -> int:
    """検知タイプの色を取得する便利関数"""
    return DetectionTypeManager.get_color(detection_type)


def get_detection_emoji(detection_type: str) -> str:
    """検知タイプの絵文字を取得する便利関数"""
    return DetectionTypeManager.get_emoji(detection_type)


# 互換性のためのレガシー定数（段階的に廃止予定）
DETECTION_TYPE_NAMES = DetectionTypeManager.get_all_detection_types()
DETECTION_TYPE_COLORS = {
    detection_type: DetectionTypeManager.get_color(detection_type)
    for detection_type in DetectionType.ALL_TYPES
}
