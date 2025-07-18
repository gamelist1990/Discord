
from typing import List, Any
from discord.ext import commands
import discord
from plugins.antiModule.spam import Block
from plugins.antiModule.config import AntiCheatConfig
from plugins.antiModule.utils import parse_duration
from plugins.antiModule.flag_commands import setup_flag_commands
from plugins.antiModule.types import DetectionTypeManager

from index import is_admin as isAdmin, load_config

# antiコマンドの実装


def setup_anti_commands(bot):
    config = load_config()

    # フラグシステムのコマンドを設定
    setup_flag_commands(bot)

    from plugins import register_command

    @commands.group()
    async def anti(ctx):
        """
        miniAnti : サーバーのスパム・荒らし対策コマンド
        詳細は #help で確認できます。
        """
        if ctx.invoked_subcommand is None:
            await ctx.send(
                "`#anti settings|bypass|unblock|block|list|alert|toggle|flag` サブコマンドを指定してください。\n例: `#anti settings`, `#anti flag`, `#anti flag quick`"
            )

    @anti.command()
    async def settings(ctx):
        """現在の設定をEmbedで表示"""
        guild = ctx.guild
        config = await AntiCheatConfig.get_config(guild)


        embed = discord.Embed(title="🛡️ miniAnti 設定", color=0x2B90D9)

        # 基本設定
        alert_channel_text = (
            f"<#{config['alert_channel']}>" if config["alert_channel"] else "未設定"
        )
        bypass_role_text = (
            f"<@&{config['bypass_role']}>" if config["bypass_role"] else "未設定"
        )

        # ホワイトリスト状態取得
        whitelist_raw = await AntiCheatConfig.get_setting(guild, "whitelist_channels")
        whitelist: List[int] = []
        if whitelist_raw is not None and type(whitelist_raw) is list:
            whitelist = [int(x) for x in whitelist_raw if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())]
        whitelist_status = f"{'✅ 有効' if len(whitelist) > 0 else '❌ 無効'} ({len(whitelist)}件)"

        embed.add_field(
            name="🔧 基本設定",
            value=f"**状態**: {'✅ 有効' if config['enabled'] else '❌ 無効'}\n"
            f"**Alert通知チャンネル**: {alert_channel_text}\n"
            f"**バイパスロール**: {bypass_role_text}\n"
            f"**ホワイトリスト**: {whitelist_status}",
            inline=False,
        )

        # 検知設定
        detection = config["detection_settings"]
        detection_status = []
        config_display_names = DetectionTypeManager.get_config_display_names()

        for config_key, display_name in config_display_names.items():
            enabled = detection.get(config_key, False)
            status_icon = "✅ 有効" if enabled else "❌ 無効"
            detection_status.append(f"{display_name}: {status_icon}")

        embed.add_field(
            name="🔍 検知機能", value="\n".join(detection_status), inline=False
        )

        embed.set_footer(
            text="設定変更: #anti toggle <機能名> | チャンネル設定: #anti alert <ID>"
        )
        await ctx.send(embed=embed)

    @anti.command()
    async def bypass(ctx, role_id=None):
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。")
            return

        if role_id is None:
            # 現在の設定を確認
            current_bypass_role = await AntiCheatConfig.get_setting(
                ctx.guild, "bypass_role"
            )
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
            await ctx.send("管理者権限が必要です。")
            return
        """指定ユーザーのblock/タイムアウトを解除"""
        await Block.handle_unblock(user_id, ctx.guild)
        await ctx.send(f"ユーザー <@{user_id}> のブロック/タイムアウトを解除しました。")

    @anti.command()
    async def block(ctx, user_id: int, duration: str):
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。")
            return
        """指定ユーザーを任意期間ブロック（例: 1m, 2h, 3d, 10s）"""
        seconds = parse_duration(duration)
        if not seconds:
            await ctx.send("期間指定が不正です。例: 1m, 2h, 3d, 10s")
            return
        from plugins.antiModule.spam import user_blocked_until, Block
        from datetime import timedelta

        user_blocked_until[user_id] = int(discord.utils.utcnow().timestamp()) + seconds
        # タイムアウトも適用
        member = None
        try:
            member = await ctx.guild.fetch_member(int(user_id))
            until = discord.utils.utcnow() + timedelta(seconds=seconds)
            if hasattr(member, "timeout"):
                await member.timeout(until, reason="管理者による手動ブロック")
        except Exception as e:
            print(f"[anti block] Timeout失敗: {user_id} {e}")
        await ctx.send(
            f"ユーザー <@{user_id}> を {duration} ブロックしました。\n直近1時間以内のメッセージを安全に削除します…"
        )
        # 直近1時間以内のメッセージ削除（ratelimit安全設計）
        try:
            from plugins.antiModule.notifier import Notifier

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
        from plugins.antiModule.spam import user_blocked_until

        now = int(discord.utils.utcnow().timestamp())
        blocks = [
            (uid, until) for uid, until in user_blocked_until.items() if until > now
        ]
        if not blocks:
            await ctx.send("現在ブロック中のユーザーはいません。")
            return
        desc = "\n".join([f"<@{uid}> (残り{until-now}秒)" for uid, until in blocks])
        embed = discord.Embed(
            title="ブロック中ユーザー", description=desc, color=0xA21CAF
        )
        await ctx.send(embed=embed)

    @anti.command()
    async def alert(ctx, channel_id=None):
        """Alert通知チャンネルを設定/確認 (null で無効化)"""
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。")
            return

        if channel_id is None:
            # 現在の設定を確認
            current_alert_channel = await AntiCheatConfig.get_setting(
                ctx.guild, "alert_channel"
            )
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

        valid_features = {"enabled": "AntiCheat全体"}
        # 動的に検知機能を追加
        valid_features.update(DetectionTypeManager.get_config_display_names())

        if feature is None:
            # 利用可能な機能を表示
            embed = discord.Embed(title="🔄 切り替え可能な機能", color=0x00BFFF)
            feature_list = []
            for key, name in valid_features.items():
                current_status = await AntiCheatConfig.get_setting(
                    ctx.guild, key if key == "enabled" else f"detection_settings.{key}"
                )
                status_icon = "✅ 有効" if current_status else "❌ 無効"
                feature_list.append(f"• `{key}` - {name} ({status_icon})")

            embed.add_field(
                name="機能一覧", value="\n".join(feature_list), inline=False
            )
            embed.add_field(
                name="使用例",
                value="`#anti toggle enabled` - AntiCheat全体の有効/無効\n"
                "`#anti toggle text_spam` - テキストスパム検知の有効/無効",
                inline=False,
            )
            await ctx.send(embed=embed)
            return

        if feature not in valid_features:
            await ctx.send(
                f"❌ 無効な機能名です。利用可能: {', '.join(valid_features.keys())}"
            )
            return

        # 現在の状態を取得
        if feature == "enabled":
            current_value = await AntiCheatConfig.get_setting(ctx.guild, "enabled")
            new_value = not current_value
            await AntiCheatConfig.update_setting(ctx.guild, "enabled", new_value)
        else:
            current_value = await AntiCheatConfig.get_setting(
                ctx.guild, f"detection_settings.{feature}"
            )
            new_value = not current_value
            await AntiCheatConfig.update_setting(
                ctx.guild, f"detection_settings.{feature}", new_value
            )

        status = "✅ 有効" if new_value else "❌ 無効"
        await ctx.send(
            f"🔄 **{valid_features[feature]}** を **{status}** に変更しました。"
        )

    @anti.command()
    async def flag(ctx, subcommand: str = "", user_id: int = 0, count: int = 0):
        """フラグシステムの設定画面を開く。'quick'を指定すると推奨設定を適用
        clearサブコマンド: #anti flag clear <user_id> [count]
        """
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("❌ 管理者権限が必要です。")
            return
        from plugins.antiModule.flag_commands import (
            _quick_setup_command,
            FlagConfigView,
        )
        from plugins.antiModule.flag_system import FlagSystem

        if subcommand == "quick":
            await _quick_setup_command(ctx)
            return
        elif subcommand == "clear":
            if not user_id:
                await ctx.send(
                    "❌ ユーザーIDを指定してください。例: `#anti flag clear 123456789012345678` または `#anti flag clear 123456789012345678 10`"
                )
                return
            member = None
            try:
                member = await ctx.guild.fetch_member(user_id)
            except Exception:
                pass
            if not member:
                await ctx.send(f"❌ 指定ユーザーが見つかりません: {user_id}")
                return
            user_flags = await FlagSystem.get_user_flags(ctx.guild, user_id)
            before = user_flags["flags"]
            if not count:
                # 全クリア
                await FlagSystem.reset_user_flags(ctx.guild, user_id)
                await ctx.send(
                    f"✅ <@{user_id}> のフラグを全てリセットしました。（元: {before}）"
                )
            else:
                if not (1 <= count <= 100):
                    await ctx.send("❌ 1～100の範囲で指定してください。")
                    return
                # 指定数だけ減算: まず全リセット→新しいフラグを1件だけ追加
                await FlagSystem.reset_user_flags(ctx.guild, user_id)
                new_flags = max(0, before - count)
                if new_flags > 0:
                    # flags_added, last_decay, violationsの最低限で追加
                    from plugins.antiModule.flag_system import FlagSystem as _FS

                    guild_id = ctx.guild.id
                    _FS._ensure_user_flags_loaded(guild_id)
                    if guild_id not in _FS._user_flags:
                        _FS._user_flags[guild_id] = {}
                    if user_id not in _FS._user_flags[guild_id]:
                        _FS._user_flags[guild_id][user_id] = []
                    _FS._user_flags[guild_id][user_id].append(
                        {
                            "flags_added": new_flags,
                            "last_decay": int(discord.utils.utcnow().timestamp()),
                            "violations": [],
                        }
                    )
                    _FS._save_user_flags_to_db(guild_id, _FS._user_flags[guild_id])
                await ctx.send(
                    f"✅ <@{user_id}> のフラグを {count} 減らしました。（{before} → {new_flags}）"
                )
            return
        elif subcommand != "":
            await ctx.send(
                "❌ 無効なサブコマンドです。使用可能: `#anti flag` `#anti flag quick` `#anti flag clear <user_id> [count]`"
            )
            return

        from plugins.antiModule.flag_commands import FlagConfigView
        from plugins.antiModule.flag_system import FlagSystem

        embed = discord.Embed(
            title="🚩 フラグシステム設定",
            description="各項目をクリックして設定を変更してください",
            color=0x3498DB,
        )

        view = FlagConfigView(ctx.guild, ctx.author.id)
        await view.setup()

        # 現在の設定概要を表示
        flag_config = await FlagSystem.get_flag_config(ctx.guild)
        status = "✅ 有効" if flag_config["enabled"] else "❌ 無効"
        embed.add_field(
            name="📊 現在の状態",
            value=f"**システム状態**: {status}\n**フラグ減衰時間**: {flag_config['decay_hours']}時間\n**設定済みアクション数**: {len(flag_config['actions'])}個",
            inline=False,
        )

        message = await ctx.send(embed=embed, view=view)
        view.message = message

    @anti.command()
    async def whitelist(ctx, action: str = "", channel_id: str = ""):
        """ホワイトリスト管理: #anti whitelist <add/remove/list> <channel_id>"""
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("管理者権限が必要です。")
            return
        if action not in ("add", "remove", "list"):
            await ctx.send("使用方法: #anti whitelist <add/remove/list> <channel_id>")
            return
        # 設定取得
        raw = await AntiCheatConfig.get_setting(ctx.guild, "whitelist_channels")
        whitelist: List[int] = []
        if raw is not None and type(raw) is list:
            whitelist = [int(x) for x in raw if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())]
        if action == "list":
            if not whitelist:
                await ctx.send("ホワイトリストに登録されたチャンネルはありません。")
            else:
                desc = "\n".join([f"<#{cid}>" for cid in whitelist])
                embed = discord.Embed(title="ホワイトリストチャンネル一覧", description=desc, color=0x2ecc71)
                await ctx.send(embed=embed)
            return
        if not channel_id:
            await ctx.send("チャンネルIDを指定してください。例: #anti whitelist add 123456789012345678")
            return
        try:
            channel_id_int = int(channel_id)
        except Exception:
            await ctx.send("チャンネルIDは数値で指定してください。")
            return
        if action == "add":
            if channel_id_int in whitelist:
                await ctx.send(f"<#{channel_id_int}> は既にホワイトリストに登録されています。")
                return
            channel = ctx.guild.get_channel(channel_id_int)
            if not channel:
                await ctx.send("指定されたチャンネルIDが見つかりません。")
                return
            whitelist.append(channel_id_int)
            await AntiCheatConfig.update_setting(ctx.guild, "whitelist_channels", whitelist)
            await ctx.send(f"<#{channel_id_int}> をホワイトリストに追加しました。")
        elif action == "remove":
            if channel_id_int not in whitelist:
                await ctx.send(f"<#{channel_id_int}> はホワイトリストに登録されていません。")
                return
            whitelist.remove(channel_id_int)
            await AntiCheatConfig.update_setting(ctx.guild, "whitelist_channels", whitelist)
            await ctx.send(f"<#{channel_id_int}> をホワイトリストから削除しました。")

    register_command(bot, anti)
