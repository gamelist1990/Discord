# フラグシステムの設定用コマンド
import discord
from plugins.common_ui import ModalInputView
from plugins.antiModule.flag_system import FlagSystem
from plugins.antiModule.types import DetectionTypeManager
from typing import Dict, Optional


class FlagConfigView(discord.ui.View):
    """フラグシステムの設定画面"""
    
    def __init__(self, guild: discord.Guild, user_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config: Dict = {}
        self.message: Optional[discord.Message] = None  # メッセージを保存するための属性を追加
    
    async def setup(self):
        """設定データを読み込む"""
        self.config = await FlagSystem.get_flag_config(self.guild)
    
    @discord.ui.button(label="🎯 フラグ重み設定", style=discord.ButtonStyle.primary, row=0)
    async def flag_weights_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🎯 フラグ重み設定",
            description="各検知タイプで付与されるフラグ数を設定します",
            color=0x3498db
        )
        
        weights = self.config["flag_weights"]
        weight_display = []
        for detection_type, weight in weights.items():
            display_name = DetectionTypeManager.get_display_name(detection_type)
            weight_display.append(f"{display_name}: **{weight}** フラグ")
        
        embed.add_field(
            name="現在の設定",
            value="\n".join(weight_display),
            inline=False
        )
        
        view = FlagWeightEditView(self.guild, self.user_id, self.config)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="⚡ アクション設定", style=discord.ButtonStyle.danger, row=0)
    async def actions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="⚡ アクション設定",
            description="フラグ数に応じて実行されるアクションを設定します",
            color=0xe74c3c
        )
        
        actions = self.config["actions"]
        action_display = []
        for i, action in enumerate(actions):
            action_types = {
                "timeout": "⏱️ 発言停止",
                "kick": "👢 サーバーから追放",
                "ban": "🔨 永久追放"
            }
            action_name = action_types.get(action["action"], action["action"])
            duration_text = ""
            if action["action"] == "timeout":
                duration = action.get("duration", 0)
                if duration >= 86400:
                    duration_text = f" ({duration//86400}日間)"
                elif duration >= 3600:
                    duration_text = f" ({duration//3600}時間)"
                elif duration >= 60:
                    duration_text = f" ({duration//60}分間)"
                else:
                    duration_text = f" ({duration}秒間)"
            
            action_display.append(f"**{action['flag_count']}** 違反ポイント → {action_name}{duration_text}")
        
        embed.add_field(
            name="現在の設定",
            value="\n".join(action_display) if action_display else "設定なし",
            inline=False
        )
        
        view = FlagActionEditView(self.guild, self.user_id, self.config)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="⚙️ 一般設定", style=discord.ButtonStyle.secondary, row=1)
    async def general_settings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="⚙️ 一般設定",
            description="フラグシステムの基本設定を変更します",
            color=0x95a5a6
        )
        
        enabled = "✅ 有効" if self.config["enabled"] else "❌ 無効"
        decay_hours = self.config["decay_hours"]
        
        embed.add_field(
            name="現在の設定",
            value=f"**状態**: {enabled}\n**フラグ減衰時間**: {decay_hours}時間",
            inline=False
        )
        
        view = FlagGeneralEditView(self.guild, self.user_id, self.config)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="📊 統計表示", style=discord.ButtonStyle.success, row=1)
    async def statistics_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        top_users = await FlagSystem.get_top_flagged_users(self.guild, 10)
        
        embed = discord.Embed(
            title="📊 フラグシステム統計",
            description="現在のフラグ状況",
            color=0xf39c12
        )
        
        if top_users:
            user_list = []
            for i, user_data in enumerate(top_users[:10], 1):
                user_id = user_data["user_id"]
                flags = user_data["flags"]
                violations = user_data["violations"]
                user_list.append(f"{i}. <@{user_id}> - **{flags}** フラグ ({violations} 違反)")
            
            embed.add_field(
                name="フラグ保有者 TOP10",
                value="\n".join(user_list),
                inline=False
            )
        else:
            embed.add_field(
                name="フラグ保有者",
                value="現在フラグを持つユーザーはいません",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class FlagWeightEditView(discord.ui.View):
    """フラグ重み編集ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
        
        # 各検知タイプのボタンを追加
        detection_types_info = DetectionTypeManager.get_flag_weight_display_names()
        
        for i, (detection_type, display_name) in enumerate(detection_types_info.items()):
            current_weight = self.config['flag_weights'].get(detection_type, 0)
            button = discord.ui.Button(
                label=f"{display_name} ({current_weight})",
                style=discord.ButtonStyle.secondary,
                custom_id=f"weight_{detection_type}",
                row=i // 3
            )
            button.callback = self.create_weight_callback(detection_type, display_name)
            self.add_item(button)
    
    def create_weight_callback(self, detection_type: str, display_name: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
                return
            
            current_weight = self.config["flag_weights"].get(detection_type, 1)
            
            async def on_submit(interaction, value, recipient, view):
                try:
                    new_weight = int(value)
                    if new_weight < 0 or new_weight > 100:
                        await interaction.followup.send("❌ フラグ重みは0-100の範囲で設定してください。", ephemeral=True)
                        return
                    
                    self.config["flag_weights"][detection_type] = new_weight
                    await FlagSystem.save_flag_config(self.guild, self.config)
                    
                    embed = discord.Embed(
                        title="✅ 設定完了",
                        description=f"{display_name}のフラグ重みを **{new_weight}** に設定しました。",
                        color=0x00ff00
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                except ValueError:
                    await interaction.followup.send("❌ 有効な数値を入力してください。", ephemeral=True)
            
            modal_view = ModalInputView(
                label=f"{display_name} 重み設定",
                modal_title="フラグ重み設定",
                text_label="フラグ重み (0-100)",
                placeholder=f"現在: {current_weight}",
                on_submit=on_submit,
                min_length=1,
                max_length=3
            )
            
            await interaction.response.send_message(
                f"**{display_name}** のフラグ重みを設定してください。\n現在の値: **{current_weight}**",
                view=modal_view,
                ephemeral=True
            )
        
        return callback


class FlagActionEditView(discord.ui.View):
    """フラグアクション編集ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
    
    @discord.ui.button(label="➕ アクション追加", style=discord.ButtonStyle.success)
    async def add_action_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        view = AddActionView(self.guild, self.user_id, self.config)
        await interaction.response.send_message("新しいアクションを追加します:", view=view, ephemeral=True)
    
    @discord.ui.button(label="🗑️ アクション削除", style=discord.ButtonStyle.danger)
    async def remove_action_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        if not self.config["actions"]:
            await interaction.response.send_message("❌ 削除できるアクションがありません。", ephemeral=True)
            return
        
        view = RemoveActionView(self.guild, self.user_id, self.config)
        await interaction.response.send_message("削除するアクションを選択してください:", view=view, ephemeral=True)
    
    @discord.ui.button(label="✏️ アクション編集", style=discord.ButtonStyle.secondary)
    async def edit_action_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        if not self.config["actions"]:
            await interaction.response.send_message("❌ 編集できるアクションがありません。", ephemeral=True)
            return
        
        view = EditActionView(self.guild, self.user_id, self.config)
        await interaction.response.send_message("編集するアクションを選択してください:", view=view, ephemeral=True)


class EditActionView(discord.ui.View):
    """アクション編集ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
        
        # ドロップダウンメニューを追加
        if config["actions"]:
            self.add_item(EditActionSelect(guild, user_id, config))


class EditActionSelect(discord.ui.Select):
    """アクション編集用ドロップダウン"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        self.guild = guild
        self.user_id = user_id
        self.config = config
        
        # ドロップダウンのオプションを作成
        options = []
        for i, action in enumerate(config["actions"][:25]):  # Discordの制限で最大25個
            action_types = {
                "timeout": "⏱️ 発言停止",
                "kick": "👢 サーバーから追放", 
                "ban": "🔨 永久追放"
            }
            
            action_name = action_types.get(action["action"], action["action"])
            duration_text = ""
            
            if action["action"] == "timeout":
                duration = action.get("duration", 0)
                if duration >= 86400:
                    duration_text = f" ({duration//86400}日間)"
                elif duration >= 3600:
                    duration_text = f" ({duration//3600}時間)"
                elif duration >= 60:
                    duration_text = f" ({duration//60}分間)"
                else:
                    duration_text = f" ({duration}秒間)"
            
            option_label = f"{action['flag_count']}違反ポイント → {action_name}{duration_text}"
            options.append(discord.SelectOption(
                label=option_label[:100],  # Discordの制限
                value=str(i),
                description=f"このアクションを編集します"
            ))
        
        super().__init__(
            placeholder="編集するアクションを選択してください...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このドロップダウンはコマンド実行者のみ使用できます。", ephemeral=True)
            return
        
        try:
            index = int(self.values[0])
            if 0 <= index < len(self.config["actions"]):
                action = self.config["actions"][index]
                view = EditSingleActionView(self.guild, self.user_id, self.config, index, action)
                
                action_types = {
                    "timeout": "発言停止",
                    "kick": "サーバーから追放",
                    "ban": "永久追放"
                }
                action_name = action_types.get(action["action"], action["action"])
                
                embed = discord.Embed(
                    title="✏️ アクション編集",
                    description=f"**{action['flag_count']}違反ポイント** の **{action_name}** を編集します",
                    color=0xf39c12
                )
                
                # 現在の設定を表示
                if action["action"] == "timeout":
                    duration = action.get("duration", 0)
                    if duration >= 86400:
                        duration_display = f"{duration//86400}日間"
                    elif duration >= 3600:
                        duration_display = f"{duration//3600}時間"
                    elif duration >= 60:
                        duration_display = f"{duration//60}分間"
                    else:
                        duration_display = f"{duration}秒間"
                    
                    embed.add_field(
                        name="現在の設定",
                        value=f"**違反ポイント**: {action['flag_count']}\n**アクション**: {action_name}\n**期間**: {duration_display}",
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="現在の設定",
                        value=f"**違反ポイント**: {action['flag_count']}\n**アクション**: {action_name}",
                        inline=False
                    )
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await interaction.response.send_message("❌ 編集に失敗しました。", ephemeral=True)
        except (ValueError, IndexError):
            await interaction.response.send_message("❌ 編集に失敗しました。", ephemeral=True)


class EditSingleActionView(discord.ui.View):
    """単一アクション編集ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict, action_index: int, action: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
        self.action_index = action_index
        self.action = action
    
    @discord.ui.button(label="🎯 違反ポイント数変更", style=discord.ButtonStyle.primary)
    async def edit_flag_count(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        current_count = self.action["flag_count"]
        
        async def on_submit(interaction, value, recipient, view):
            try:
                new_count = int(value)
                if new_count < 1 or new_count > 1000:
                    await interaction.followup.send("❌ 違反ポイント数は1-1000の範囲で設定してください。", ephemeral=True)
                    return
                
                self.config["actions"][self.action_index]["flag_count"] = new_count
                self.config["actions"].sort(key=lambda x: x["flag_count"])
                await FlagSystem.save_flag_config(self.guild, self.config)
                
                embed = discord.Embed(
                    title="✅ 編集完了",
                    description=f"違反ポイント数を **{current_count}** から **{new_count}** に変更しました。",
                    color=0x00ff00
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except ValueError:
                await interaction.followup.send("❌ 有効な数値を入力してください。", ephemeral=True)
        
        modal_view = ModalInputView(
            label="違反ポイント数変更",
            modal_title="違反ポイント数設定",
            text_label="新しい違反ポイント数",
            placeholder=f"現在: {current_count}",
            on_submit=on_submit,
            min_length=1,
            max_length=4
        )
        
        await interaction.response.send_message(
            f"新しい違反ポイント数を入力してください。\n現在の値: **{current_count}**",
            view=modal_view,
            ephemeral=True
        )
    
    @discord.ui.button(label="⚡ アクション種類変更", style=discord.ButtonStyle.secondary)
    async def edit_action_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        view = ActionTypeChangeView(self.guild, self.user_id, self.config, self.action_index, self.action)
        await interaction.response.send_message("新しいアクション種類を選択してください:", view=view, ephemeral=True)
    
    @discord.ui.button(label="⏰ 期間変更", style=discord.ButtonStyle.success)
    async def edit_duration(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        if self.action["action"] != "timeout":
            await interaction.response.send_message("❌ 期間設定は発言停止アクションのみ可能です。", ephemeral=True)
            return
        
        current_duration = self.action.get("duration", 0)
        
        async def on_submit(interaction, duration_str, recipient, view):
            try:
                duration = parse_duration(duration_str)
                if duration < 1 or duration > 2419200:  # 最大28日
                    await interaction.followup.send("❌ 期間は1秒-2419200秒(28日)の範囲で設定してください。", ephemeral=True)
                    return
                
                # 現在の期間を読みやすい形式で表示
                if current_duration >= 86400:
                    old_display = f"{current_duration//86400}日間"
                elif current_duration >= 3600:
                    old_display = f"{current_duration//3600}時間"
                elif current_duration >= 60:
                    old_display = f"{current_duration//60}分間"
                else:
                    old_display = f"{current_duration}秒間"
                
                # 新しい期間を読みやすい形式で表示
                if duration >= 86400:
                    new_display = f"{duration//86400}日間"
                elif duration >= 3600:
                    new_display = f"{duration//3600}時間"
                elif duration >= 60:
                    new_display = f"{duration//60}分間"
                else:
                    new_display = f"{duration}秒間"
                
                self.config["actions"][self.action_index]["duration"] = duration
                await FlagSystem.save_flag_config(self.guild, self.config)
                
                embed = discord.Embed(
                    title="✅ 編集完了",
                    description=f"期間を **{old_display}** から **{new_display}** に変更しました。",
                    color=0x00ff00
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except ValueError as e:
                await interaction.followup.send(f"❌ 期間の形式が正しくありません。\n例: `300`, `5m`, `1h`, `1d`\nエラー: {str(e)}", ephemeral=True)
        
        duration_modal = ModalInputView(
            label="期間変更",
            modal_title="発言停止期間設定",
            text_label="新しい期間",
            placeholder="例: 300, 5m, 1h, 1d",
            on_submit=on_submit,
            min_length=1,
            max_length=10
        )
        
        # 現在の期間を読みやすい形式で表示
        if current_duration >= 86400:
            current_display = f"{current_duration//86400}日間"
        elif current_duration >= 3600:
            current_display = f"{current_duration//3600}時間"
        elif current_duration >= 60:
            current_display = f"{current_duration//60}分間"
        else:
            current_display = f"{current_duration}秒間"
        
        await interaction.response.send_message(
            f"新しい発言停止期間を入力してください:\n現在: **{current_display}**\n\n"
            f"📝 **入力例:**\n"
            f"• `300` (300秒)\n"
            f"• `5m` (5分)\n"
            f"• `1h` (1時間)\n"
            f"• `1d` (1日)",
            view=duration_modal,
            ephemeral=True
        )


class ActionTypeChangeView(discord.ui.View):
    """アクション種類変更ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict, action_index: int, action: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
        self.action_index = action_index
        self.action = action
    
    @discord.ui.button(label="⏱️ 発言停止", style=discord.ButtonStyle.primary)
    async def change_to_timeout(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change_action_type(interaction, "timeout")
    
    @discord.ui.button(label="👢 サーバーから追放", style=discord.ButtonStyle.secondary)
    async def change_to_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change_action_type(interaction, "kick")
    
    @discord.ui.button(label="🔨 永久追放", style=discord.ButtonStyle.danger)
    async def change_to_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._change_action_type(interaction, "ban")
    
    async def _change_action_type(self, interaction: discord.Interaction, new_action_type: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        action_names = {
            "timeout": "発言停止",
            "kick": "サーバーから追放",
            "ban": "永久追放"
        }
        
        old_action_name = action_names.get(self.action["action"], self.action["action"])
        new_action_name = action_names[new_action_type]
        
        if new_action_type == "timeout":
            # 発言停止の場合は期間を設定
            if self.action["action"] == "timeout":
                # すでに発言停止の場合はそのまま
                await interaction.response.send_message("❌ すでに発言停止アクションです。", ephemeral=True)
                return
            
            async def on_duration_submit(interaction, duration_str, recipient, view):
                try:
                    duration = parse_duration(duration_str)
                    if duration < 1 or duration > 2419200:  # 最大28日
                        await interaction.followup.send("❌ 期間は1秒-2419200秒(28日)の範囲で設定してください。", ephemeral=True)
                        return
                    
                    self.config["actions"][self.action_index]["action"] = new_action_type
                    self.config["actions"][self.action_index]["duration"] = duration
                    self.config["actions"][self.action_index]["message"] = f"{self.action['flag_count']}違反ポイントによる{new_action_name}です。"
                    await FlagSystem.save_flag_config(self.guild, self.config)
                    
                    # 期間を読みやすい形式で表示
                    if duration >= 86400:
                        duration_display = f"{duration//86400}日間"
                    elif duration >= 3600:
                        duration_display = f"{duration//3600}時間"
                    elif duration >= 60:
                        duration_display = f"{duration//60}分間"
                    else:
                        duration_display = f"{duration}秒間"
                    
                    embed = discord.Embed(
                        title="✅ 編集完了",
                        description=f"アクションを **{old_action_name}** から **{new_action_name}({duration_display})** に変更しました。",
                        color=0x00ff00
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                except ValueError as e:
                    await interaction.followup.send(f"❌ 期間の形式が正しくありません。\n例: `300`, `5m`, `1h`, `1d`\nエラー: {str(e)}", ephemeral=True)
            
            duration_modal = ModalInputView(
                label="期間設定",
                modal_title="発言停止期間設定",
                text_label="期間",
                placeholder="例: 300, 5m, 1h, 1d",
                on_submit=on_duration_submit,
                min_length=1,
                max_length=10
            )
            
            await interaction.response.send_message(
                f"**{new_action_name}** の期間を入力してください:\n\n"
                f"📝 **入力例:**\n"
                f"• `300` (300秒)\n"
                f"• `5m` (5分)\n"
                f"• `1h` (1時間)\n"
                f"• `1d` (1日)",
                view=duration_modal,
                ephemeral=True
            )
        else:
            # キック・永久追放の場合は期間不要
            self.config["actions"][self.action_index]["action"] = new_action_type
            self.config["actions"][self.action_index]["message"] = f"{self.action['flag_count']}違反ポイントによる{new_action_name}です。"
            
            # duration フィールドを削除（キック・BANの場合）
            if "duration" in self.config["actions"][self.action_index]:
                del self.config["actions"][self.action_index]["duration"]
            
            await FlagSystem.save_flag_config(self.guild, self.config)
            
            embed = discord.Embed(
                title="✅ 編集完了",
                description=f"アクションを **{old_action_name}** から **{new_action_name}** に変更しました。",
                color=0x00ff00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class AddActionView(discord.ui.View):
    """アクション追加ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
    
    @discord.ui.button(label="⏱️ 発言停止", style=discord.ButtonStyle.primary)
    async def timeout_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_action(interaction, "timeout")
    
    @discord.ui.button(label="👢 サーバーから追放", style=discord.ButtonStyle.secondary)
    async def kick_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_action(interaction, "kick")
    
    @discord.ui.button(label="🔨 永久追放", style=discord.ButtonStyle.danger)
    async def ban_action(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._add_action(interaction, "ban")
    
    async def _add_action(self, interaction: discord.Interaction, action_type: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        action_names = {
            "timeout": "発言停止",
            "kick": "サーバーから追放", 
            "ban": "永久追放"
        }
        
        # フラグ数設定
        async def on_flag_submit(interaction, flag_count_str, recipient, view):
            try:
                flag_count = int(flag_count_str)
                if flag_count < 1 or flag_count > 1000:
                    await interaction.followup.send("❌ フラグ数は1-1000の範囲で設定してください。", ephemeral=True)
                    return
                
                if action_type == "timeout":
                    # タイムアウトの場合は期間も設定
                    async def on_duration_submit(interaction, duration_str, recipient, view):
                        try:
                            duration = parse_duration(duration_str)
                            if duration < 1 or duration > 2419200:  # 最大28日
                                await interaction.followup.send("❌ 期間は1秒-2419200秒(28日)の範囲で設定してください。", ephemeral=True)
                                return
                            
                            # アクションを追加
                            new_action = {
                                "flag_count": flag_count,
                                "action": action_type,
                                "duration": duration,
                                "message": f"{flag_count}違反ポイントによる{action_names[action_type]}です。"
                            }
                            
                            self.config["actions"].append(new_action)
                            self.config["actions"].sort(key=lambda x: x["flag_count"])
                            await FlagSystem.save_flag_config(self.guild, self.config)
                            
                            # 期間を読みやすい形式で表示
                            if duration >= 86400:
                                duration_display = f"{duration//86400}日間"
                            elif duration >= 3600:
                                duration_display = f"{duration//3600}時間"
                            elif duration >= 60:
                                duration_display = f"{duration//60}分間"
                            else:
                                duration_display = f"{duration}秒間"
                            
                            embed = discord.Embed(
                                title="✅ アクション追加完了",
                                description=f"**{flag_count}** 違反ポイントで **{action_names[action_type]}({duration_display})** を追加しました。",
                                color=0x00ff00
                            )
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                            
                        except ValueError as e:
                            await interaction.followup.send(f"❌ 期間の形式が正しくありません。\n例: `300`, `5m`, `1h`, `1d`\nエラー: {str(e)}", ephemeral=True)
                    
                    duration_modal = ModalInputView(
                        label="期間設定",
                        modal_title="発言停止期間設定",
                        text_label="期間",
                        placeholder="例: 300, 5m, 1h, 1d (秒/分/時間/日)",
                        on_submit=on_duration_submit,
                        min_length=1,
                        max_length=10
                    )
                    
                    await interaction.response.send_message(
                        f"**{flag_count}** 違反ポイントでの**発言停止期間**を入力してください:\n\n"
                        f"📝 **入力例:**\n"
                        f"• `300` (300秒)\n"
                        f"• `5m` (5分)\n"
                        f"• `1h` (1時間)\n"
                        f"• `1d` (1日)",
                        view=duration_modal,
                        ephemeral=True
                    )
                else:
                    # キック・永久追放の場合は期間不要
                    new_action = {
                        "flag_count": flag_count,
                        "action": action_type,
                        "message": f"{flag_count}違反ポイントによる{action_names[action_type]}です。"
                    }
                    
                    self.config["actions"].append(new_action)
                    self.config["actions"].sort(key=lambda x: x["flag_count"])
                    await FlagSystem.save_flag_config(self.guild, self.config)
                    
                    embed = discord.Embed(
                        title="✅ アクション追加完了",
                        description=f"**{flag_count}** 違反ポイントで **{action_names[action_type]}** を追加しました。",
                        color=0x00ff00
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except ValueError:
                await interaction.followup.send("❌ 有効な数値を入力してください。", ephemeral=True)
        
        flag_modal = ModalInputView(
            label=f"{action_names[action_type]} 設定",
            modal_title="違反ポイント数設定",
            text_label="必要な違反ポイント数",
            placeholder="例: 5, 10, 20",
            on_submit=on_flag_submit,
            min_length=1,
            max_length=4
        )
        
        await interaction.response.send_message(
            f"**{action_names[action_type]}** を実行する**違反ポイント数**を入力してください:",
            view=flag_modal,
            ephemeral=True
        )


class RemoveActionView(discord.ui.View):
    """アクション削除ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
        
        # ドロップダウンメニューを追加
        if config["actions"]:
            self.add_item(RemoveActionSelect(guild, user_id, config))


class RemoveActionSelect(discord.ui.Select):
    """アクション削除用ドロップダウン"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        self.guild = guild
        self.user_id = user_id
        self.config = config
        
        # ドロップダウンのオプションを作成
        options = []
        for i, action in enumerate(config["actions"][:25]):  # Discordの制限で最大25個
            action_types = {
                "timeout": "⏱️ 発言停止",
                "kick": "👢 サーバーから追放", 
                "ban": "🔨 永久追放"
            }
            
            action_name = action_types.get(action["action"], action["action"])
            duration_text = ""
            
            if action["action"] == "timeout":
                duration = action.get("duration", 0)
                if duration >= 86400:
                    duration_text = f" ({duration//86400}日間)"
                elif duration >= 3600:
                    duration_text = f" ({duration//3600}時間)"
                elif duration >= 60:
                    duration_text = f" ({duration//60}分間)"
                else:
                    duration_text = f" ({duration}秒間)"
            
            option_label = f"{action['flag_count']}違反ポイント → {action_name}{duration_text}"
            options.append(discord.SelectOption(
                label=option_label[:100],  # Discordの制限
                value=str(i),
                description=f"このアクションを削除します"
            ))
        
        super().__init__(
            placeholder="削除するアクションを選択してください...",
            options=options,
            min_values=1,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このドロップダウンはコマンド実行者のみ使用できます。", ephemeral=True)
            return
        
        try:
            index = int(self.values[0])
            if 0 <= index < len(self.config["actions"]):
                removed_action = self.config["actions"].pop(index)
                await FlagSystem.save_flag_config(self.guild, self.config)
                
                action_types = {
                    "timeout": "発言停止",
                    "kick": "サーバーから追放",
                    "ban": "永久追放"
                }
                action_name = action_types.get(removed_action["action"], removed_action["action"])
                
                embed = discord.Embed(
                    title="✅ アクション削除完了",
                    description=f"**{removed_action['flag_count']}** 違反ポイントの **{action_name}** を削除しました。",
                    color=0x00ff00
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message("❌ 削除に失敗しました。", ephemeral=True)
        except (ValueError, IndexError):
            await interaction.response.send_message("❌ 削除に失敗しました。", ephemeral=True)


class FlagGeneralEditView(discord.ui.View):
    """一般設定編集ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int, config: Dict):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
        self.config = config
    
    @discord.ui.button(label="🔄 有効/無効切り替え", style=discord.ButtonStyle.primary)
    async def toggle_enabled(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        self.config["enabled"] = not self.config["enabled"]
        await FlagSystem.save_flag_config(self.guild, self.config)
        
        status = "✅ 有効" if self.config["enabled"] else "❌ 無効"
        embed = discord.Embed(
            title="✅ 設定変更完了",
            description=f"フラグシステムを **{status}** に変更しました。",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="⏰ 減衰時間設定", style=discord.ButtonStyle.secondary)
    async def decay_hours_setting(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        current_hours = self.config["decay_hours"]
        
        async def on_submit(interaction, value, recipient, view):
            try:
                new_hours = int(value)
                if new_hours < 1 or new_hours > 8760:  # 最大1年
                    await interaction.followup.send("❌ 減衰時間は1-8760時間の範囲で設定してください。", ephemeral=True)
                    return
                
                self.config["decay_hours"] = new_hours
                await FlagSystem.save_flag_config(self.guild, self.config)
                
                embed = discord.Embed(
                    title="✅ 設定完了",
                    description=f"フラグ減衰時間を **{new_hours}時間** に設定しました。",
                    color=0x00ff00
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                
            except ValueError:
                await interaction.followup.send("❌ 有効な数値を入力してください。", ephemeral=True)
        
        modal_view = ModalInputView(
            label="減衰時間設定",
            modal_title="フラグ減衰時間設定",
            text_label="減衰時間 (時間)",
            placeholder=f"現在: {current_hours}時間",
            on_submit=on_submit,
            min_length=1,
            max_length=4
        )
        
        await interaction.response.send_message(
            f"フラグが自動減少する時間を設定してください。\n現在の値: **{current_hours}時間**",
            view=modal_view,
            ephemeral=True
        )


def setup_flag_commands(bot):
    """フラグシステムのコマンドを追加"""
    from index import is_admin as isAdmin, load_config
    config = load_config()
    
    @bot.command(name="flaginfo")
    async def flaginfo_command(ctx, user: Optional[discord.Member] = None):
        """ユーザーのフラグ情報を表示"""
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("❌ 管理者権限が必要です。")
            return
        
        target_user = user if user is not None else ctx.author
        
        flag_data = await FlagSystem.get_user_flags(ctx.guild, target_user.id)
        
        embed = discord.Embed(
            title=f"🚩 {target_user.display_name} のフラグ情報",
            color=0xe74c3c if flag_data["flags"] > 0 else 0x2ecc71
        )
        
        embed.add_field(
            name="現在のフラグ数",
            value=f"**{flag_data['flags']}** フラグ",
            inline=True
        )
        
        embed.add_field(
            name="違反履歴",
            value=f"**{len(flag_data['violations'])}** 件",
            inline=True
        )
        
        if flag_data["violations"]:
            violations_text = []
            for violation in flag_data["violations"][-5:]:  # 最新5件
                from datetime import datetime
                dt = datetime.fromtimestamp(violation["timestamp"])
                timestamp = discord.utils.format_dt(dt, style="R")
                violations_text.append(f"• {violation['type']} (+{violation['flags_added']}) {timestamp}")
            
            embed.add_field(
                name="最近の違反 (最新5件)",
                value="\n".join(violations_text),
                inline=False
            )
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        await ctx.send(embed=embed)
    
    # フラグメインコマンドは commands.py で定義されているため削除
    
    @bot.command(name="flagreset")
    async def flagreset_command(ctx, user: discord.Member):
        """ユーザーのフラグをリセット"""
        if not isAdmin(str(ctx.author.id), str(ctx.guild.id), config):
            await ctx.send("❌ 管理者権限が必要です。")
            return
        
        success = await FlagSystem.reset_user_flags(ctx.guild, user.id)
        
        if success:
            embed = discord.Embed(
                title="✅ フラグリセット完了",
                description=f"{user.mention} のフラグをリセットしました。",
                color=0x00ff00
            )
        else:
            embed = discord.Embed(
                title="ℹ️ フラグリセット",
                description=f"{user.mention} のフラグはありませんでした。",
                color=0x3498db
            )
        
        await ctx.send(embed=embed)

def parse_duration(duration_str: str) -> int:
    """期間文字列を秒数に変換"""
    duration_str = duration_str.strip().lower()
    
    # 数値のみの場合はそのまま秒として扱う
    if duration_str.isdigit():
        return int(duration_str)
    
    # 単位付きの場合
    import re
    match = re.match(r'^(\d+)([smhd])$', duration_str)
    if match:
        value = int(match.group(1))
        unit = match.group(2)
        
        if unit == 's':  # 秒
            return value
        elif unit == 'm':  # 分
            return value * 60
        elif unit == 'h':  # 時間
            return value * 3600
        elif unit == 'd':  # 日
            return value * 86400
    
    # 日本語単位の場合
    japanese_units = {
        '秒': 1,
        '分': 60,
        '時間': 3600,
        '日': 86400
    }
    
    for unit, multiplier in japanese_units.items():
        if duration_str.endswith(unit):
            try:
                value = int(duration_str[:-len(unit)])
                return value * multiplier
            except ValueError:
                continue
    
    # パースに失敗した場合は例外を発生
    raise ValueError(f"無効な期間形式: {duration_str}")

async def _quick_setup_command(ctx):
    """クイック設定コマンドの実装"""
    embed = discord.Embed(
        title="⚡ クイック設定",
        description="サーバーおすすめの設定を適用しますか？\n\n"
                   "この設定では段階的に厳しくなるペナルティシステムを導入します：",
        color=0xf39c12
    )
    
    recommended_settings = [
        "5 🚩：一時的なミュート（5分間）",
        "10 🚩：一時的なミュート（10分間）", 
        "15 🚩：一時的なミュート（15分間）",
        "20 🚩：一時的なミュート（1時間）",
        "25 🚩：一時的なミュート（2時間）",
        "30 🚩：一時的なミュート（1日間）",
        "35 🚩：一時的なミュート（2日間）",
        "40 🚩：一時的なミュート（6日間）",
        "50 🚩：一時的なミュート（12日間）",
        "60 🚩：一時的なミュート（24日間）",
        "70 🚩：サーバーからキック（追い出し）"
    ]
    
    embed.add_field(
        name="📋 おすすめアクション設定",
        value="\n".join(recommended_settings),
        inline=False
    )
    
    weight_settings = [
        "📝 テキストスパム: 1 🚩",
        "🖼️ 画像スパム: 2 🚩", 
        "👥 メンションスパム: 3 🚩",
        "🔐 トークンスパム: 5 🚩",
        "⏰ 時間制限スパム: 2 🚩",
        "⌨️ 入力バイパス: 3 🚩",
        "📤 転送スパム: 2 🚩"
    ]
    
    embed.add_field(
        name="⚖️ 検知重み設定",
        value="\n".join(weight_settings),
        inline=False
    )
    
    embed.add_field(
        name="⚙️ その他設定",
        value="**減衰時間**: 24時間\n**システム**: 有効",
        inline=False
    )
    
    view = QuickSetupView(ctx.guild, ctx.author.id)
    await ctx.send(embed=embed, view=view)


class QuickSetupView(discord.ui.View):
    """クイック設定ビュー"""
    
    def __init__(self, guild: discord.Guild, user_id: int):
        super().__init__(timeout=300)
        self.guild = guild
        self.user_id = user_id
    
    @discord.ui.button(label="✅ 適用する", style=discord.ButtonStyle.success)
    async def apply_quick_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            # おすすめ設定を適用
            recommended_config = {
                "enabled": True,
                "decay_hours": 24,
                "flag_weights": {
                    "text": 1,
                    "image": 2,
                    "mention": 3,
                    "token": 5,
                    "timebase": 2,
                    "typing_bypass": 3,
                    "forward": 2
                },
                "actions": [
                    {"flag_count": 5, "action": "timeout", "duration": 300, "message": "5違反ポイントによる発言停止です。"},  # 5分
                    {"flag_count": 10, "action": "timeout", "duration": 600, "message": "10違反ポイントによる発言停止です。"},  # 10分
                    {"flag_count": 15, "action": "timeout", "duration": 900, "message": "15違反ポイントによる発言停止です。"},  # 15分
                    {"flag_count": 20, "action": "timeout", "duration": 3600, "message": "20違反ポイントによる発言停止です。"},  # 1時間
                    {"flag_count": 25, "action": "timeout", "duration": 7200, "message": "25違反ポイントによる発言停止です。"},  # 2時間
                    {"flag_count": 30, "action": "timeout", "duration": 86400, "message": "30違反ポイントによる発言停止です。"},  # 1日
                    {"flag_count": 35, "action": "timeout", "duration": 172800, "message": "35違反ポイントによる発言停止です。"},  # 2日
                    {"flag_count": 40, "action": "timeout", "duration": 518400, "message": "40違反ポイントによる発言停止です。"},  # 6日
                    {"flag_count": 50, "action": "timeout", "duration": 1036800, "message": "50違反ポイントによる発言停止です。"},  # 12日
                    {"flag_count": 60, "action": "timeout", "duration": 2073600, "message": "60違反ポイントによる発言停止です。"},  # 24日
                    {"flag_count": 70, "action": "kick", "message": "70違反ポイントによるサーバーから追放です。"}  # キック
                ]
            }
            
            await FlagSystem.save_flag_config(self.guild, recommended_config)
            
            embed = discord.Embed(
                title="✅ クイック設定完了",
                description="サーバーおすすめの設定を適用しました！",
                color=0x00ff00
            )
            
            embed.add_field(
                name="適用された設定",
                value="✅ 11段階のペナルティシステム\n"
                     "✅ バランス調整された検知重み\n"
                     "✅ 24時間の自動減衰\n"
                     "✅ システム有効化",
                inline=False
            )
            
            embed.add_field(
                name="📌 注意事項",
                value="設定はいつでも `#anti flag` コマンドで変更できます。\n"
                     "必要に応じて個別調整を行ってください。",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"[QuickSetup] Error: {e}")
            embed = discord.Embed(
                title="❌ 設定エラー",
                description="クイック設定の適用中にエラーが発生しました。",
                color=0xe74c3c
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="❌ キャンセル", style=discord.ButtonStyle.danger)
    async def cancel_quick_setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ このボタンはコマンド実行者のみ押せます。", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="❌ キャンセル",
            description="クイック設定をキャンセルしました。",
            color=0x95a5a6
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
