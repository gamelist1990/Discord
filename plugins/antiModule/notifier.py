import discord
import asyncio
from plugins.antiModule.types import DetectionTypeManager, DetectionType

class Notifier:
    def __init__(self, message):
        self.message = message

    async def send_alert_notification(self, alert_type="text", deleted_count=0):
        """
        Alert通知チャンネルにスパム検知のアラートを送信し、該当ユーザーにタイムアウト罰則も実施
        """
        try:
            # AntiCheatConfigを使用してAlert通知チャンネル設定を取得
            from .config import AntiCheatConfig
            
            # Alert通知チャンネル設定を取得
            alert_channel_id = await AntiCheatConfig.get_setting(self.message.guild, "alert_channel")
            if not alert_channel_id:
                # 設定されていない場合は何もしない
                return
            
            # アラートチャンネルを取得
            alert_channel = self.message.guild.get_channel(alert_channel_id)
            if not alert_channel:
                # チャンネルが見つからない場合は何もしない
                print(f"[miniAnti] Alert channel {alert_channel_id} not found")
                return
              # アラート種別に応じた色とアイコンを設定
            # types.pyで定義された情報を使用
            info = DetectionTypeManager.get_info(alert_type)
            config = {
                "color": info.color,
                "icon": info.emoji,
                "title": f"{info.name}検知"
            }
            
            # 大人数スパム用の特別な処理
            is_mass_spam = alert_type.startswith("mass_") or alert_type == "mass_spam"
            
            # アラートEmbed作成
            embed = discord.Embed(
                title=f"{config['icon']} {config['title']}",
                color=config["color"],
                timestamp=discord.utils.utcnow()
            )
            
            if is_mass_spam:
                # 大人数スパム時は緊急度を強調
                embed.add_field(
                    name="⚠️ 緊急度",
                    value="**HIGH - 大人数による組織的攻撃**",
                    inline=False
                )
                
                embed.add_field(
                    name="検知タイプ",
                    value=f"`{alert_type}`",
                    inline=True
                )
                
                if deleted_count > 0:
                    embed.add_field(
                        name="処理されたメッセージ数",
                        value=f"**{deleted_count}件**",
                        inline=True
                    )
                
                embed.add_field(
                    name="対象チャンネル",
                    value=self.message.channel.mention,
                    inline=True
                )
                
                embed.add_field(
                    name="実施済み対処",
                    value="• 強化slowmode適用\n• 関与ユーザー一括タイムアウト\n• メッセージ一括削除",
                    inline=False
                )
                
            else:
                # 個人スパム時の通常処理
                embed.add_field(
                    name="ユーザー",
                    value=f"{self.message.author.mention} ({self.message.author})",
                    inline=True
                )
                
                embed.add_field(
                    name="チャンネル",
                    value=self.message.channel.mention,
                    inline=True
                )
                
                if deleted_count > 0:
                    embed.add_field(
                        name="削除されたメッセージ数",
                        value=f"{deleted_count}件",
                        inline=True
                    )
                
                if self.message.content and len(self.message.content) > 0:
                    content_preview = self.message.content[:100] + "..." if len(self.message.content) > 100 else self.message.content
                    embed.add_field(
                        name="メッセージ内容",
                        value=f"```{content_preview}```",
                        inline=False
                    )
                
                embed.set_footer(text=f"User ID: {self.message.author.id}")
            
            # アラート送信
            await alert_channel.send(embed=embed)
            
            if is_mass_spam:
                print(f"[miniAnti] MASS SPAM Alert sent to #{alert_channel.name}: type={alert_type}, processed={deleted_count}")
            else:
                print(f"[miniAnti] Alert sent to #{alert_channel.name}: user={self.message.author} type={alert_type}")

        except Exception as e:
            print(f"[miniAnti] Failed to send alert notification: {e}")

    async def send_image_spam_warning(self):
        embed = discord.Embed(
            title="画像スパム警告",
            description="⚠️ 画像によるスパム行為が検出されたため、一時的にチャットが制限されます。約30分後に解除されます。",
            color=0xF59E42,
        )
        try:
            await self.message.reply(embed=embed, ephemeral=True)
        except Exception:
            pass

    async def purge_user_messages(self, alert_type="text", deleted=None):
        """
        アンチチートで検知された全ての処理で共通: 直近1時間以内のユーザーのメッセージを最大10件削除し、DMでEmbed通知（クールタイム付き）
        alert_type: 'text' or 'image' など警告種別
        deleted: Noneまたはint。Noneなら削除処理を行い、intならその件数で通知のみ
        """
        try:
            from datetime import datetime, timezone, timedelta as dt_timedelta

            deleted_count = 0
            channel = self.message.channel
            now = datetime.now(timezone.utc)
            # 削除件数が指定されていなければ実際に削除
            if deleted is None:
                DELETE_LIMIT = 10
                count = 0
                async for msg in channel.history(limit=100):
                    if msg.author.id == self.message.author.id:
                        if (
                            msg.created_at
                            and (now - msg.created_at).total_seconds() <= 3600
                        ):
                            try:
                                await msg.delete()
                                deleted_count += 1
                                count += 1
                                await asyncio.sleep(1.2)
                                if count >= DELETE_LIMIT:
                                    break
                            except Exception:
                                pass
            else:
                deleted_count = deleted
            
            # Alert通知チャンネルにアラート送信
            await self.send_alert_notification(alert_type, deleted_count)
            
            # DM通知（Embed形式・クールタイム付き）
            if not hasattr(self, "_last_dm_notify"):
                self._last_dm_notify = 0
            dm_cooldown = 60
            now_ts = now.timestamp()
            # クールタイム中はDMを送らず削除のみ行う
            if now_ts - getattr(self, "_last_dm_notify", 0) > dm_cooldown:
                try:
                    embed_dm = discord.Embed(
                        title="警告: 荒らし行為",
                        description=(
                            f"あなたの荒らし行為が検知されました。\n"
                            f"Type: {alert_type}\n"
                            f"直近1時間以内のメッセージ{deleted_count}件が削除されました。\n"
                            f"チャンネル: {channel.mention}\n"
                            "今後同様の行為が続く場合、より厳しい措置が取られる可能性があります。"
                        ),
                        color=0xA21CAF,
                    )
                    await self.message.author.send(embed=embed_dm)
                    print(f"[miniAnti] DM送信: user={self.message.author} id={self.message.author.id} type={alert_type} deleted={deleted_count}")
                    self._last_dm_notify = now_ts
                except Exception:
                    pass
            # クールタイム中は何も送らない
        except Exception:
            pass

