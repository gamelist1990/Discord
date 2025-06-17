from discord.ext import commands
import discord
import asyncio
from discord import Embed, ButtonStyle, Interaction, SelectOption
from discord.ui import View, Button, Select, Modal, TextInput
from plugins import register_command
from index import load_config, is_admin
from datetime import datetime


def setup(bot):
    class MainEditView(View):
        def __init__(self, ctx):
            super().__init__(timeout=170)
            self.ctx = ctx
            self.author_id = ctx.author.id

        @discord.ui.button(label="🔐 権限設定", style=ButtonStyle.primary, emoji="🔐")
        async def permission_settings(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            
            embed = Embed(
                title="🔐 権限設定",
                description="対象となるロールを選択してください",
                color=0x5865f2
            )
            view = RoleSelectView(self.ctx, self.author_id)
            await interaction.response.edit_message(embed=embed, view=view)

        @discord.ui.button(label="❌ 閉じる", style=ButtonStyle.danger)
        async def close_panel(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return 
            
            embed = Embed(
                title="✅ 設定パネルを閉じました",
                description="操作が完了しました。",
                color=0x57f287
            )
            await interaction.response.edit_message(embed=embed, view=None)

    class RoleSelectView(View):
        def __init__(self, ctx, author_id):
            super().__init__(timeout=170)
            self.ctx = ctx
            self.author_id = author_id
            self.add_item(RoleDropdown(ctx, author_id))

        @discord.ui.button(label="🔙 戻る", style=ButtonStyle.secondary)
        async def back_to_main(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            
            embed = Embed(
                title="⚙️ サーバー設定編集",
                description="設定したい項目を選択してください",
                color=0x5865f2
            )
            view = MainEditView(self.ctx)
            await interaction.response.edit_message(embed=embed, view=view)

    class RoleDropdown(Select):
        def __init__(self, ctx, author_id):
            self.ctx = ctx
            self.author_id = author_id
            
            # オプションを作成
            options = [
                SelectOption(
                    label="@everyone (デフォルト)",
                    value="everyone",
                    description="サーバー全体のデフォルト権限",
                    emoji="👥"
                )
            ]
            
            # ロールを追加（最大24個まで）
            roles = sorted(ctx.guild.roles[1:], key=lambda r: r.position, reverse=True)[:23]  # @everyoneを除く
            for role in roles:
                if not role.is_bot_managed():  # Bot管理ロールを除外
                    options.append(
                        SelectOption(
                            label=f"@{role.name}",
                            value=str(role.id),
                            description=f"ポジション: {role.position}",
                            emoji="🎭"
                        )
                    )
            
            super().__init__(
                placeholder="権限を設定するロールを選択...",
                options=options,
                min_values=1,
                max_values=1
            )

        async def callback(self, interaction: Interaction):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            
            selected_value = self.values[0]
            
            if selected_value == "everyone":
                role_name = "@everyone"
                target_role = self.ctx.guild.default_role
            else:
                target_role = self.ctx.guild.get_role(int(selected_value))
                role_name = f"@{target_role.name}" if target_role else "不明なロール"
            
            if not target_role:
                await interaction.response.send_message("❌ ロールが見つかりません。", ephemeral=True)
                return
            
            embed = Embed(
                title=f"🔐 {role_name} の権限設定",
                description="設定したい権限を選択してください",
                color=target_role.color if target_role.color.value != 0 else 0x5865f2
            )
            
            view = PermissionEditView(self.ctx, self.author_id, target_role)
            await interaction.response.edit_message(embed=embed, view=view)

    class PermissionEditView(View):
        def __init__(self, ctx, author_id, target_role):
            super().__init__(timeout=170)
            self.ctx = ctx
            self.author_id = author_id
            self.target_role = target_role

        @discord.ui.button(label="🤖 外部のアプリコマンドの使用", style=ButtonStyle.secondary, emoji="🤖")
        async def toggle_use_external_application_commands(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=Embed(
                    title="🤖 外部のアプリコマンドの使用 権限設定",
                    description="有効/無効を選択してください",
                    color=0x5865f2
                ),
                view=PermissionConfirmView(self.ctx, self.author_id, self.target_role, "use_external_apps", "外部のアプリコマンドの使用"),
                ephemeral=True
            )

        @discord.ui.button(label="🛠️ アプリコマンドの使用", style=ButtonStyle.secondary, emoji="🛠️")
        async def toggle_use_application_commands(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=Embed(
                    title="🛠️ アプリコマンドの使用 権限設定",
                    description="有効/無効を選択してください",
                    color=0x5865f2
                ),
                view=PermissionConfirmView(self.ctx, self.author_id, self.target_role, "use_application_commands", "アプリコマンドの使用"),
                ephemeral=True
            )

        @discord.ui.button(label="📨 招待の作成", style=ButtonStyle.secondary, emoji="📨")
        async def toggle_create_invite(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=Embed(
                    title="📨 招待の作成 権限設定",
                    description="有効/無効を選択してください",
                    color=0x5865f2
                ),
                view=PermissionConfirmView(self.ctx, self.author_id, self.target_role, "create_instant_invite", "招待の作成"),
                ephemeral=True
            )

        @discord.ui.button(label="💬 チャットの禁止", style=ButtonStyle.secondary, emoji="💬")
        async def toggle_chat_ban(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=Embed(
                    title="💬 チャットの禁止 権限設定",
                    description="有効/無効を選択してください",
                    color=0x5865f2
                ),
                view=PermissionConfirmView(self.ctx, self.author_id, self.target_role, "send_messages", "チャットの禁止"),
                ephemeral=True
            )

        @discord.ui.button(label="🗳️ 投票の作成", style=ButtonStyle.secondary, emoji="🗳️")
        async def toggle_create_vote(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=Embed(
                    title="🗳️ 投票の作成 権限設定",
                    description="有効/無効を選択してください",
                    color=0x5865f2
                ),
                view=PermissionConfirmView(self.ctx, self.author_id, self.target_role, "create_polls", "投票の作成"),
                ephemeral=True
            )

        @discord.ui.button(label="🔙 戻る", style=ButtonStyle.primary, row=1)
        async def back_to_role_select(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            
            embed = Embed(
                title="🔐 権限設定",
                description="対象となるロールを選択してください",
                color=0x5865f2
            )
            view = RoleSelectView(self.ctx, self.author_id)
            await interaction.response.edit_message(embed=embed, view=view)

    class PermissionConfirmView(View):
        def __init__(self, ctx, author_id, target_role, permission_name, permission_display):
            super().__init__(timeout=90)
            self.ctx = ctx
            self.author_id = author_id
            self.target_role = target_role
            self.permission_name = permission_name
            self.permission_display = permission_display

        @discord.ui.button(label="✅ 有効にする", style=ButtonStyle.success)
        async def enable_permission(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            await self._apply_permission(interaction, True)

        @discord.ui.button(label="🚫 無効にする", style=ButtonStyle.danger)
        async def disable_permission(self, interaction: Interaction, button: Button):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            await self._apply_permission(interaction, False)

        async def _apply_permission(self, interaction: Interaction, value: bool):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("❌ この操作はコマンド実行者のみ可能です。", ephemeral=True)
                return
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message("⏳ 権限を一括更新中です...", ephemeral=True)
                else:
                    await interaction.followup.send("⏳ 権限を一括更新中です...", ephemeral=True)
                channels_updated = 0
                categories_updated = 0
                failed_channels = []
                batch_size = 5
                channels = [ch for ch in self.ctx.guild.channels if isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.ForumChannel, discord.StageChannel))]
                for i in range(0, len(channels), batch_size):
                    batch = channels[i:i+batch_size]
                    tasks = [self._set_channel_permission(ch, value, failed_channels) for ch in batch]
                    results = await asyncio.gather(*tasks)
                    for is_category in results:
                        if is_category is True:
                            categories_updated += 1
                        elif is_category is False:
                            channels_updated += 1
                    await asyncio.sleep(1)  # バッチごとに1秒待機（レートリミット対策）
                status = "🟢 ON" if value else "🔴 OFF"
                role_name = "@everyone" if self.target_role == self.ctx.guild.default_role else f"@{self.target_role.name}"
                embed = Embed(
                    title="✅ 権限が更新されました",
                    description=f"**{role_name}** の **{self.permission_display}** を {status} に設定しました",
                    color=0x57f287,
                    timestamp=datetime.now()
                )
                embed.add_field(
                    name="📊 適用範囲",
                    value=f"チャンネル: {channels_updated}個\nカテゴリ: {categories_updated}個",
                    inline=True
                )
                if failed_channels:
                    embed.add_field(
                        name="⚠️ 失敗したチャンネル",
                        value=f"{len(failed_channels)}個のチャンネルで更新に失敗しました",
                        inline=True
                    )
                await interaction.edit_original_response(content=None, embed=embed, view=None)
            except discord.Forbidden:
                embed = Embed(
                    title="❌ 権限エラー",
                    description="この操作を実行する権限がありません。Botの権限を確認してください。",
                    color=0xed4245
                )
                await interaction.edit_original_response(content=None, embed=embed, view=None)
            except Exception as e:
                embed = Embed(
                    title="❌ エラーが発生しました",
                    description=f"```{str(e)}```",
                    color=0xed4245
                )
                await interaction.edit_original_response(content=None, embed=embed, view=None)

        async def _set_channel_permission(self, channel: discord.abc.GuildChannel, value: bool, failed_channels: list):
            try:
                overwrite = channel.overwrites_for(self.target_role)
                setattr(overwrite, self.permission_name, value)
                await channel.set_permissions(
                    self.target_role,
                    overwrite=overwrite,
                    reason="Botによる権限一括変更"
                )
                await asyncio.sleep(0.05)  # レートリミット対策
                return isinstance(channel, discord.CategoryChannel)
            except Exception:
                failed_channels.append(channel.name)
                return None

    @commands.command()
    async def edit(ctx):
        """
        サーバー設定を編集するための管理者専用コマンド。
        権限設定などをインタラクティブに行えます。
        ※通常のテキストコマンドはephemeral不可。ボタン等の操作はephemeralで実行者のみに案内されます。
        """
        config = load_config()
        if not is_admin(str(ctx.author.id), ctx.guild.id, config):
            reply_msg = await ctx.reply('❌ あなたは管理者権限を持っていません。', mention_author=False)
            await asyncio.sleep(5)
            await reply_msg.delete()
            return
        embed = Embed(
            title="⚙️ サーバー設定編集",
            description="設定したい項目を選択してください\n\n**利用可能な機能:**\n🔐 権限設定 - ロールごとの詳細権限管理",
            color=0x5865f2,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"実行者: {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        view = MainEditView(ctx)
        reply_msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        await asyncio.sleep(300)
        try:
            await reply_msg.delete()
        except:
            pass

    register_command(bot, edit, aliases=None, admin=True)
