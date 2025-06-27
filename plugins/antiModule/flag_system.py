# フラグシステム - ユーザーの違反に対してフラグを蓄積し、段階的なアクションを実行
import json
from typing import Dict, List, Optional, Union
from datetime import datetime, timedelta
import discord
from discord.ext import commands
from plugins.antiModule.config import AntiCheatConfig
from DataBase import get_guild_data, set_guild_data, update_guild_data


class FlagSystem:
    """
    フラグシステムの管理クラス
    各検知でフラグを蓄積し、一定のフラグ数に達したらアクションを実行
    """
    
    DEFAULT_FLAG_CONFIG = {
        "enabled": True,
        "decay_hours": 24, 
        "flag_weights": {
            "text": 0,
            "image": 0,
            "mention": 0,
            "token": 0,
            "timebase": 0,
            "typing_bypass": 0,
            "forward": 0
        },
        "actions": []  
    }
    
    # ユーザーのフラグデータ: {guild_id: {user_id: {"flags": int, "last_decay": timestamp, "violations": []}}}
    _user_flags: Dict[int, Dict[int, Dict]] = {}
    
    @classmethod
    async def get_flag_config(cls, guild) -> Dict:
        """ギルドのフラグ設定を取得"""
        try:
            config = await AntiCheatConfig.get_setting(guild, "flag_system", cls.DEFAULT_FLAG_CONFIG)
            if not config:
                return cls.DEFAULT_FLAG_CONFIG.copy()
            
            # デフォルト設定とマージ
            merged_config = cls.DEFAULT_FLAG_CONFIG.copy()
            cls._deep_merge(merged_config, config)
            return merged_config
        except Exception as e:
            print(f"[FlagSystem] Failed to load config: {e}")
            return cls.DEFAULT_FLAG_CONFIG.copy()
    
    @classmethod
    async def save_flag_config(cls, guild, config: Dict):
        """ギルドのフラグ設定を保存"""
        try:
            await AntiCheatConfig.update_setting(guild, "flag_system", config)
            print(f"[FlagSystem] Config saved for guild {guild.name}")
        except Exception as e:
            print(f"[FlagSystem] Failed to save config: {e}")
    
    @classmethod
    def _deep_merge(cls, base_dict: Dict, update_dict: Dict):
        """辞書の深いマージ"""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                cls._deep_merge(base_dict[key], value)
            else:
                base_dict[key] = value
    
    @classmethod
    def _load_user_flags_from_db(cls, guild_id):
        """DBから該当ギルドのユーザーフラグ情報を読み込む"""
        data = get_guild_data(guild_id)
        return data.get("user_flags", {})

    @classmethod
    def _save_user_flags_to_db(cls, guild_id, user_flags):
        """DBに該当ギルドのユーザーフラグ情報を書き込む（既存データとマージ）"""
        data = get_guild_data(guild_id)
        existing_flags = data.get("user_flags", {})
        # ユーザーごとにマージ
        merged_flags = existing_flags.copy()
        for user_id, new_flag in user_flags.items():
            if user_id in merged_flags and isinstance(merged_flags[user_id], dict) and isinstance(new_flag, dict):
                # violationsリストは結合し重複を除去
                old_violations = merged_flags[user_id].get("violations", [])
                new_violations = new_flag.get("violations", [])
                # message_idで重複除去
                seen = set()
                merged_violations = []
                for v in old_violations + new_violations:
                    mid = v.get("message_id")
                    if mid is None or mid not in seen:
                        merged_violations.append(v)
                        if mid is not None:
                            seen.add(mid)
                merged_flags[user_id] = {
                    **merged_flags[user_id],
                    **new_flag,
                    "violations": merged_violations
                }
            else:
                merged_flags[user_id] = new_flag
        data["user_flags"] = merged_flags
        set_guild_data(guild_id, data)

    @classmethod
    def _ensure_user_flags_loaded(cls, guild_id):
        """DBからメモリにロード（初回のみ）"""
        if guild_id not in cls._user_flags:
            cls._user_flags[guild_id] = cls._load_user_flags_from_db(guild_id)

    @classmethod
    async def add_flag(cls, message: discord.Message, alert_type: str) -> bool:
        """
        ユーザーにフラグを追加し、必要に応じてアクションを実行
        
        Args:
            message: Discord message object
            alert_type: 検知タイプ ("text", "image", "mention", "token", "timebase", "typing_bypass", "forward")
        
        Returns:
            bool: アクションが実行されたかどうか
        """
        if not message.guild or message.author.bot:
            return False
        
        config = await cls.get_flag_config(message.guild)
        if not config.get("enabled", True):
            return False
        
        guild_id = message.guild.id
        user_id = message.author.id
        cls._ensure_user_flags_loaded(guild_id)
        
        # ギルドデータを初期化
        if guild_id not in cls._user_flags:
            cls._user_flags[guild_id] = {}
        
        # ユーザーデータを初期化
        if user_id not in cls._user_flags[guild_id]:
            cls._user_flags[guild_id][user_id] = {
                "flags": 0,
                "last_decay": datetime.now().timestamp(),
                "violations": []
            }
        user_data = cls._user_flags[guild_id][user_id]
        
        # フラグの自動減衰処理
        await cls._apply_flag_decay(user_data, config)
        
        # フラグを追加
        flag_weight = config["flag_weights"].get(alert_type, 1)
        user_data["flags"] += flag_weight
        user_data["violations"].append({
            "type": alert_type,
            "timestamp": datetime.now().timestamp(),
            "flags_added": flag_weight,
            "channel_id": message.channel.id,
            "message_id": message.id
        })
        # DBに保存
        cls._save_user_flags_to_db(guild_id, cls._user_flags[guild_id])
        print(f"[FlagSystem] User {user_id} in guild {guild_id}: +{flag_weight} flags ({alert_type}), total: {user_data['flags']}")
        
        # アクションを実行
        return await cls._execute_action(message, user_data["flags"], config)
    
    @classmethod
    async def _apply_flag_decay(cls, user_data: Dict, config: Dict):
        """フラグの自動減衰を適用"""
        now = datetime.now().timestamp()
        last_decay = user_data["last_decay"]
        decay_hours = config.get("decay_hours", 24)
        
        hours_passed = (now - last_decay) / 3600
        if hours_passed >= decay_hours:
            # 1日経過するごとに1フラグ減少
            decay_amount = int(hours_passed / decay_hours)
            user_data["flags"] = max(0, user_data["flags"] - decay_amount)
            user_data["last_decay"] = now
            
            if decay_amount > 0:
                print(f"[FlagSystem] Applied flag decay: -{decay_amount} flags")
    
    @classmethod
    async def _execute_action(cls, message: discord.Message, flag_count: int, config: Dict) -> bool:
        """フラグ数に応じてアクションを実行"""
        actions = config.get("actions", [])
        
        # フラグ数の多い順にソートして、該当するアクションを見つける
        applicable_actions = [action for action in actions if flag_count >= action["flag_count"]]
        if not applicable_actions:
            return False
        
        # 最も高いフラグ数のアクションを実行
        action = max(applicable_actions, key=lambda x: x["flag_count"])
        
        try:
            # message.authorがMemberかどうかを確認
            if not isinstance(message.author, discord.Member):
                print(f"[FlagSystem] Cannot execute action: author is not a Member")
                return False
            
            member = message.author
            action_type = action["action"]
            action_message = action.get("message", f"違反行為により{action_type}が実行されました。")
            guild_name = message.guild.name if message.guild else "Unknown Server"
            
            if action_type == "timeout":
                duration = action.get("duration", 300)
                until = discord.utils.utcnow() + timedelta(seconds=duration)
                await member.timeout(until, reason=f"フラグシステム: {flag_count}フラグ")
                
                # DMで通知
                try:
                    await member.send(f"🚨 **{guild_name}**\n{action_message}")
                except:
                    pass
                
                # チャンネルに通知
                embed = discord.Embed(
                    title="🚨 フラグシステム - タイムアウト",
                    description=f"{member.mention} が {flag_count} フラグに達したため、{duration}秒間のタイムアウトが実行されました。",
                    color=0xff6b00
                )
                await message.channel.send(embed=embed)
                
            elif action_type == "kick":
                await member.kick(reason=f"フラグシステム: {flag_count}フラグ")
                
                # DMで通知
                try:
                    await member.send(f"🚨 **{guild_name}**\n{action_message}")
                except:
                    pass
                
                # チャンネルに通知
                embed = discord.Embed(
                    title="🚨 フラグシステム - キック",
                    description=f"{member.mention} が {flag_count} フラグに達したため、サーバーからキックされました。",
                    color=0xff3333
                )
                await message.channel.send(embed=embed)
                
            elif action_type == "ban":
                await member.ban(reason=f"フラグシステム: {flag_count}フラグ", delete_message_days=1)
                
                # DMで通知（BANの場合は送信できない可能性が高い）
                try:
                    await member.send(f"🚨 **{guild_name}**\n{action_message}")
                except:
                    pass
                
                # チャンネルに通知
                embed = discord.Embed(
                    title="🚨 フラグシステム - BAN",
                    description=f"{member.mention} が {flag_count} フラグに達したため、サーバーからBANされました。",
                    color=0x8b0000
                )
                await message.channel.send(embed=embed)
            
            print(f"[FlagSystem] Executed {action_type} for user {member.id} with {flag_count} flags")
            return True
            
        except Exception as e:
            action_type = action.get("action", "unknown") if 'action' in locals() else "unknown"
            print(f"[FlagSystem] Failed to execute action {action_type}: {e}")
            return False
    
    @classmethod
    async def get_user_flags(cls, guild: discord.Guild, user_id: int) -> Dict:
        """ユーザーのフラグ情報を取得"""
        guild_id = guild.id
        cls._ensure_user_flags_loaded(guild_id)
        if guild_id not in cls._user_flags or user_id not in cls._user_flags[guild_id]:
            return {"flags": 0, "violations": []}
        
        user_data = cls._user_flags[guild_id][user_id]
        config = await cls.get_flag_config(guild)
        
        # 減衰を適用
        await cls._apply_flag_decay(user_data, config)
        # DBに保存（減衰反映）
        cls._save_user_flags_to_db(guild_id, cls._user_flags[guild_id])
        
        return {
            "flags": user_data["flags"],
            "violations": user_data["violations"][-10:]  # 最新10件のみ
        }
    
    @classmethod
    async def reset_user_flags(cls, guild: discord.Guild, user_id: int) -> bool:
        """ユーザーのフラグをリセット"""
        guild_id = guild.id
        cls._ensure_user_flags_loaded(guild_id)
        if guild_id in cls._user_flags and user_id in cls._user_flags[guild_id]:
            cls._user_flags[guild_id][user_id] = {
                "flags": 0,
                "last_decay": datetime.now().timestamp(),
                "violations": []
            }
            cls._save_user_flags_to_db(guild_id, cls._user_flags[guild_id])
            return True
        return False
    
    @classmethod
    async def get_top_flagged_users(cls, guild: discord.Guild, limit: int = 10) -> List[Dict]:
        """フラグの多いユーザー上位を取得"""
        guild_id = guild.id
        cls._ensure_user_flags_loaded(guild_id)
        if guild_id not in cls._user_flags:
            return []
        
        config = await cls.get_flag_config(guild)
        users_with_flags = []
        
        for user_id, user_data in cls._user_flags[guild_id].items():
            # 減衰を適用
            await cls._apply_flag_decay(user_data, config)
            
            if user_data["flags"] > 0:
                users_with_flags.append({
                    "user_id": user_id,
                    "flags": user_data["flags"],
                    "violations": len(user_data["violations"])
                })
        
        # DBに保存（減衰反映）
        cls._save_user_flags_to_db(guild_id, cls._user_flags[guild_id])
        # フラグ数でソート
        users_with_flags.sort(key=lambda x: x["flags"], reverse=True)
        return users_with_flags[:limit]
