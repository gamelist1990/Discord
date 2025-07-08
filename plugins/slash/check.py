import discord
import typing
from discord import app_commands
from plugins import registerSlashCommand
from lib.op import OP_EVERYONE
from plugins.antiModule.flag_system import FlagSystem
from plugins.antiModule.types import DetectionTypeManager
from typing import Optional


def setup(bot):
    async def check_callback(interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """ユーザーの現在のフラグ数と次のアクションを表示（シンプル版）"""
        if not interaction.guild:
            await interaction.response.send_message("❌ このコマンドはサーバー内でのみ使用できます。", ephemeral=True)
            return
        
        # 対象ユーザーを設定（指定されていない場合は自分自身）
        target_user = user if user else interaction.user
        
        try:
            # ユーザーのフラグ情報を取得
            flag_data = await FlagSystem.get_user_flags(interaction.guild, target_user.id)
            current_flags = flag_data["flags"]
            violations = flag_data["violations"]
            
            # フラグシステムの設定を取得
            config = await FlagSystem.get_flag_config(interaction.guild)
            
            # フラグシステムが無効の場合
            if not config.get("enabled", True):
                embed = discord.Embed(
                    title="📊 フラグ確認",
                    description="🔒 フラグシステムは現在無効です。",
                    color=0x95a5a6
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # 次のアクションを計算
            next_action_info = _get_next_action_info(current_flags, config.get("actions", []))
            
            # Embedを作成
            embed = discord.Embed(
                title="📊 フラグ状況チェック",
                description=f"**{target_user.display_name}** さんの現在の状況",
                color=_get_flag_color(current_flags, next_action_info)
            )
            
            # ユーザーのアバターを設定
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            # プログレスバー表示
            progress_bar = _create_flag_progress_bar(current_flags, next_action_info)
            embed.add_field(
                name="🚩 フラグ状況",
                value=progress_bar,
                inline=False
            )
            
            # 基本情報のみ（シンプル版）
            basic_info = f"📋 **違反件数:** {len(violations)}件\n"
            basic_info += f"🚩 **現在フラグ:** {current_flags}個"
            
            if next_action_info:
                flags_needed = next_action_info["flag_count"] - current_flags
                action_types = {
                    "timeout": "⏱️ タイムアウト",
                    "kick": "👢 キック", 
                    "ban": "🔨 BAN"
                }
                action_name = action_types.get(next_action_info["action"], next_action_info["action"])
                
                if flags_needed <= 0:
                    basic_info += f"\n⚠️ **次のアクション:** {action_name} (即実行可能)"
                else:
                    basic_info += f"\n⚡ **次のアクション:** {action_name} (あと{flags_needed}フラグ)"
            else:
                basic_info += "\n✅ **処罰設定:** なし"
            
            embed.add_field(
                name="📊 基本情報",
                value=basic_info,
                inline=True
            )
            
            # 最新違反のみ表示（シンプル版）
            if violations:
                recent_violation = violations[-1]
                from datetime import datetime
                dt = datetime.fromtimestamp(recent_violation["timestamp"])
                timestamp = discord.utils.format_dt(dt, style="R")
                
                type_name = DetectionTypeManager.get_display_name(recent_violation["type"])
                type_emoji = DetectionTypeManager.get_emoji(recent_violation["type"])
                
                last_violation_info = f"{type_emoji} **{type_name}**\n"
                last_violation_info += f"⏰ {timestamp}\n"
                last_violation_info += f"🚩 +{recent_violation['flags_added']}フラグ"
                
                embed.add_field(
                    name="📜 最新違反",
                    value=last_violation_info,
                    inline=True
                )
            else:
                embed.add_field(
                    name="✅ 違反履歴",
                    value="🌟 **違反なし**\n優良ユーザーです！",
                    inline=True
                )
            
            # フッター情報を追加（日本時間で表示）
            from datetime import datetime, timezone, timedelta
            jst = timezone(timedelta(hours=9))
            current_time = datetime.now(jst)
            time_str = current_time.strftime("%Y年%m月%d日 %H:%M:%S")
            
            embed.set_footer(
                text=f"実行時刻: {time_str} (JST)",
                icon_url=interaction.guild.icon.url if interaction.guild.icon else None
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"[CheckCommand] Error: {e}")
            embed = discord.Embed(
                title="❌ エラー",
                description="フラグ情報の取得中にエラーが発生しました。",
                color=0xe74c3c
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # checkコマンドのコールバック関数
    async def check_command_callback(interaction: discord.Interaction, user: typing.Optional[discord.Member] = None):
        await check_callback(interaction, user)
    
    # スラッシュコマンドを引数付きで登録
    registerSlashCommand(
        bot, 
        "check", 
        "フラグ数と次のアクションを確認します。他のユーザーも指定可能です。", 
        check_command_callback,
        parameters=[{
            "name": "user",
            "description": "フラグ情報を確認したいユーザー（省略した場合は自分自身）",
            "type": discord.Member,
            "required": False
        }],
        op_level=OP_EVERYONE
    )


def _create_flag_progress_bar(current_flags: int, next_action_info: Optional[dict], length: int = 15) -> str:
    """シンプルなフラグプログレスバーを作成"""
    if not next_action_info:
        return "```\n🟢 制限なし\n```"
    
    target_flags = next_action_info["flag_count"]
    if target_flags <= 0:
        return "```\n❌ 設定エラー\n```"
    
    # プログレスの計算
    progress = min(current_flags / target_flags, 1.0)
    filled_length = int(length * progress)
    
    # バーの作成
    filled_char = "█"
    empty_char = "░"
    
    bar = filled_char * filled_length + empty_char * (length - filled_length)
    
    # パーセンテージ
    percentage = int(progress * 100)
    
    # 危険度に応じた色分け
    if current_flags >= target_flags:
        status = "🔴 DANGER"
    elif percentage >= 80:
        status = "🟠 WARNING"
    elif percentage >= 50:
        status = "🟡 CAUTION"
    else:
        status = "🟢 SAFE"
    
    return f"```\n{bar} {percentage:3d}%\n```{status} ({current_flags}/{target_flags})"


def _get_next_action_info(current_flags: int, actions: list) -> Optional[dict]:
    """現在のフラグ数から次のアクションを取得"""
    if not actions:
        return None
    
    # フラグ数でソート
    sorted_actions = sorted(actions, key=lambda x: x["flag_count"])
    
    # 現在のフラグ数より大きい最小のアクションを探す
    for action in sorted_actions:
        if action["flag_count"] > current_flags:
            return action
    
    # 全てのアクションを超えている場合は最大のアクションを返す
    if sorted_actions:
        return sorted_actions[-1]
    
    return None


def _get_flag_color(current_flags: int, next_action_info: Optional[dict]) -> int:
    """フラグ数に応じた色を取得"""
    if current_flags == 0:
        return 0x2ecc71  # 緑 - 安全
    elif next_action_info and current_flags >= next_action_info["flag_count"]:
        return 0xe74c3c  # 赤 - 危険
    elif next_action_info and (next_action_info["flag_count"] - current_flags) <= 2:
        return 0xf39c12  # 橙 - 警告
    else:
        return 0x3498db  # 青 - 注意
