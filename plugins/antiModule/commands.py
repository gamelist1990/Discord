from discord.ext import commands
import discord
from . import Spam, MediaSpam, MentionSpam, TokenSpam, TimebaseSpam, Block, Griefing, GuildConfig, MiniAntiBypass, AntiCheatConfig
from .utils import parse_duration, mention_to_id
import sys
sys.path.append("../..")
from index import is_admin as isAdmin, load_config

# antiコマンドの実装

def setup_anti_commands(bot):
    config = load_config()
    @commands.group()
    async def anti(ctx):
        """
        miniAnti : サーバーのスパム・荒らし対策コマンド
        詳細は #help で確認できます。
        """
        if ctx.invoked_subcommand is None:
            await ctx.send("`#anti settings|bypass|unblock|block|list|alert|toggle` サブコマンドを指定してください。例: `#anti settings`")

    @anti.command()
    async def settings(ctx):
        """現在の設定をEmbedで表示"""
        guild = ctx.guild
        config = await AntiCheatConfig.get_config(guild)
        
        embed = discord.Embed(title="🛡️ miniAnti 設定", color=0x2b90d9)
        
        # 基本設定
        alert_channel_text = f"<#{config['alert_channel']}>" if config['alert_channel'] else "未設定"
        bypass_role_text = f"<@&{config['bypass_role']}>" if config['bypass_role'] else "未設定"
        
        embed.add_field(
            name="🔧 基本設定",
            value=f"**状態**: {'✅ 有効' if config['enabled'] else '❌ 無効'}\n"
                  f"**Alert通知チャンネル**: {alert_channel_text}\n"
                  f"**バイパスロール**: {bypass_role_text}",
            inline=False
        )
        
        # 検知設定
        detection = config['detection_settings']
        detection_status = []
        detection_status.append(f"📝 テキストスパム: {'✅ 有効' if detection['text_spam'] else '❌ 無効'}")
        detection_status.append(f"🖼️ 画像スパム: {'✅ 有効' if detection['image_spam'] else '❌ 無効'}")
        detection_status.append(f"📢 メンションスパム: {'✅ 有効' if detection['mention_spam'] else '❌ 無効'}")
        detection_status.append(f"🚨 cl/Webhookスパム: {'✅ 有効' if detection['token_spam'] else '❌ 無効'}")
        detection_status.append(f"⏰ タイムベーススパム: {'✅ 有効' if detection['timebase_spam'] else '❌ 無効'}")
        
        embed.add_field(
            name="🔍 検知機能",
            value="\n".join(detection_status),
            inline=False
        )
        
        embed.set_footer(text="設定変更: #anti toggle <機能名> | チャンネル設定: #anti alert <ID>")
        await ctx.send(embed=embed)

    @anti.command()
    async def bypass(ctx, role_id=None):
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。")
            return
        
        if role_id is None:
            # 現在の設定を確認
            current_bypass_role = await AntiCheatConfig.get_setting(ctx.guild, "bypass_role")
            if current_bypass_role:
                await ctx.send(f"現在のバイパスロール: <@&{current_bypass_role}>")
            else:
                await ctx.send("バイパスロールは未設定です。")
            return
        
        if role_id is not None:
            try:
                role_id = int(role_id)
            except (ValueError, TypeError):
                await ctx.send("❌ ロールIDは数値で指定してください。")
                return
            current = await AntiCheatConfig.get_setting(ctx.guild, "bypass_role")
            if current == role_id:
                await ctx.send(f"バイパスロールは既に <@&{role_id}> です。")
                return
        """指定ロールをbypass（スパム判定除外）に設定"""
        await AntiCheatConfig.update_setting(ctx.guild, "bypass_role", role_id)
        await ctx.send(f"バイパスロールを <@&{role_id}> に設定しました。")

    @anti.command()
    async def unblock(ctx, user_id: int):
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。"); return
        """指定ユーザーのblock/タイムアウトを解除"""
        await Block.handle_unblock(user_id, ctx.guild)
        await ctx.send(f"ユーザー <@{user_id}> のブロック/タイムアウトを解除しました。")

    @anti.command()
    async def block(ctx, user_id: int, duration: str):
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。"); return
        """指定ユーザーを任意期間ブロック（例: 1m, 2h, 3d, 10s）"""
        seconds = parse_duration(duration)
        if not seconds:
            await ctx.send("期間指定が不正です。例: 1m, 2h, 3d, 10s")
            return
        from .spam import user_blocked_until, Block
        from datetime import timedelta
        user_blocked_until[user_id] = int(discord.utils.utcnow().timestamp()) + seconds
        # タイムアウトも適用
        member = None
        try:
            member = await ctx.guild.fetch_member(int(user_id))
            until = discord.utils.utcnow() + timedelta(seconds=seconds)
            if hasattr(member, 'timeout'):
                await member.timeout(until, reason="管理者による手動ブロック")
        except Exception as e:
            print(f"[anti block] Timeout失敗: {user_id} {e}")
        await ctx.send(f"ユーザー <@{user_id}> を {duration} ブロックしました。\n直近1時間以内のメッセージを安全に削除します…")
        # 直近1時間以内のメッセージ削除（ratelimit安全設計）
        try:
            from .notifier import Notifier
            dummy_msg = ctx.message
            if member is not None:
                dummy_msg.author = member
            else:
                dummy_msg.author = ctx.guild.get_member(user_id)
            dummy_msg.guild = ctx.guild
            dummy_msg.channel = ctx.channel
            await Notifier(dummy_msg).purge_user_messages(alert_type="manual")
        except Exception as e:
            print(f"[anti block] メッセージ削除失敗: {user_id} {e}")

    @anti.command()
    async def list(ctx):
        """現在ブロック中のユーザー一覧を表示"""
        from .spam import user_blocked_until
        now = int(discord.utils.utcnow().timestamp())
        blocks = [(uid, until) for uid, until in user_blocked_until.items() if until > now]
        if not blocks:
            await ctx.send("現在ブロック中のユーザーはいません。")
            return
        desc = "\n".join([f"<@{uid}> (残り{until-now}秒)" for uid, until in blocks])
        embed = discord.Embed(title="ブロック中ユーザー", description=desc, color=0xA21CAF)
        await ctx.send(embed=embed)

    @anti.command()
    async def alert(ctx, channel_id = None):
        """Alert通知チャンネルを設定/確認 (null で無効化)"""
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。")
            return
        
        if channel_id is None:
            # 現在の設定を確認
            current_alert_channel = await AntiCheatConfig.get_setting(ctx.guild, "alert_channel")
            if current_alert_channel:
                await ctx.send(f"現在のAlert通知チャンネル: <#{current_alert_channel}>")
            else:
                await ctx.send("Alert通知チャンネルは未設定です。")
            return
        
        # nullの場合は設定を無効化
        if str(channel_id).lower() == "null":
            current = await AntiCheatConfig.get_setting(ctx.guild, "alert_channel")
            if current is None:
                await ctx.send("Alert通知チャンネルは既に無効です。")
                return
            await AntiCheatConfig.update_setting(ctx.guild, "alert_channel", None)
            await ctx.send("Alert通知チャンネルの設定を無効化しました。")
            return
        
        # チャンネルIDが有効か確認
        try:
            channel_id = int(channel_id)
            current = await AntiCheatConfig.get_setting(ctx.guild, "alert_channel")
            if current == channel_id:
                await ctx.send(f"Alert通知チャンネルは既に <#{channel_id}> です。")
                return
            channel = ctx.guild.get_channel(channel_id)
            if not channel:
                await ctx.send("指定されたチャンネルIDが見つかりません。")
                return
            # 設定を保存
            await AntiCheatConfig.update_setting(ctx.guild, "alert_channel", channel_id)
            await ctx.send(f"Alert通知チャンネルを <#{channel_id}> に設定しました。")
        except ValueError:
            await ctx.send("チャンネルIDは数値または 'null' を指定してください。")
        except Exception as e:
            await ctx.send(f"エラーが発生しました: {str(e)}")

    @anti.command()
    async def toggle(ctx, feature=None):
        """機能の有効/無効を切り替え"""
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。")
            return
        
        valid_features = {
            "enabled": "AntiCheat全体",
            "text_spam": "テキストスパム検知",
            "image_spam": "画像スパム検知", 
            "mention_spam": "メンションスパム検知",
            "token_spam": "トークン/Webhookスパム検知",
            "timebase_spam": "タイムベーススパム検知"
        }
        
        if feature is None:
            # 利用可能な機能を表示
            embed = discord.Embed(title="🔄 切り替え可能な機能", color=0x00BFFF)
            feature_list = []
            for key, name in valid_features.items():
                current_status = await AntiCheatConfig.get_setting(ctx.guild, 
                    key if key == "enabled" else f"detection_settings.{key}")
                status_icon = "✅ 有効" if current_status else "❌ 無効"
                feature_list.append(f"• `{key}` - {name} ({status_icon})")
            
            embed.add_field(
                name="機能一覧",
                value="\n".join(feature_list),
                inline=False
            )
            embed.add_field(
                name="使用例",
                value="`#anti toggle enabled` - AntiCheat全体の有効/無効\n"
                      "`#anti toggle text_spam` - テキストスパム検知の有効/無効",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        if feature not in valid_features:
            await ctx.send(f"❌ 無効な機能名です。利用可能: {', '.join(valid_features.keys())}")
            return
        
        # 現在の状態を取得
        if feature == "enabled":
            current_value = await AntiCheatConfig.get_setting(ctx.guild, "enabled")
            new_value = not current_value
            await AntiCheatConfig.update_setting(ctx.guild, "enabled", new_value)
        else:
            current_value = await AntiCheatConfig.get_setting(ctx.guild, f"detection_settings.{feature}")
            new_value = not current_value
            await AntiCheatConfig.update_setting(ctx.guild, f"detection_settings.{feature}", new_value)
        
        status = "✅ 有効" if new_value else "❌ 無効"
        await ctx.send(f"🔄 **{valid_features[feature]}** を **{status}** に変更しました。")

    bot.add_command(anti)

