import discord
from lib.op import get_op_level, has_op, OP_STAFF, OP_GUILD_ADMIN, OP_GLOBAL_ADMIN

class StaffUtil:
    def __init__(self, ctx):
        self.ctx = ctx
        self.guild = ctx.guild
        self._role = None

    def get_staff_role(self):
        if self._role is not None:
            return self._role
        from DataBase import get_guild_value
        staff_role_id = get_guild_value(self.guild.id, "staffRole")
        if not staff_role_id:
            return None
        self._role = discord.utils.get(self.guild.roles, id=int(staff_role_id))
        return self._role

    async def is_admin_user(self):
        return has_op(self.ctx.author, OP_GUILD_ADMIN)

    async def is_staff(self):
        return has_op(self.ctx.author, OP_STAFF)

    def get_staff_members(self):
        role = self.get_staff_role()
        if not role:
            return []
        return [m for m in self.guild.members if role in m.roles and not m.bot]

    async def send_staff_alert(self, message, embed=None):
        from DataBase import get_guild_value
        alert_channel_id = get_guild_value(self.guild.id, "alertChannel")
        if alert_channel_id:
            channel = self.guild.get_channel(int(alert_channel_id))
            if channel and channel.id != self.ctx.channel.id:
                if embed:
                    await channel.send(content=message if message else None, embed=embed)
                else:
                    await channel.send(message)

    @staticmethod
    def parse_timestr(timestr):
        """
        例: '10s', '5m', '2h', '1d' などを秒数に変換。数字のみならint変換。
        """
        import re
        timestr = str(timestr).strip().lower()
        pattern = r"^(\d+)([smhd]?)$"
        match = re.match(pattern, timestr)
        if not match:
            raise ValueError("時間指定は 10s, 5m, 2h, 1d などで入力してください")
        value, unit = match.groups()
        value = int(value)
        if unit == "s" or unit == "":
            return value
        elif unit == "m":
            return value * 60
        elif unit == "h":
            return value * 3600
        elif unit == "d":
            return value * 86400
        else:
            raise ValueError("不正な時間単位です")

    @staticmethod
    def get_status_emoji(status):
        """
        Discordのステータスからアイコンを返す（🟢=online, 🌙=idle, ⛔=dnd, ⚫=offline, ❔=不明）
        """
        import discord
        if status is None:
            return "❔"
        if status == discord.Status.online:
            return "🟢"
        elif status == discord.Status.idle:
            return "🌙"
        elif status == discord.Status.dnd:
            return "⛔"
        elif status == discord.Status.offline:
            return "⚫"
        else:
            return "❔"

    async def vote_action(self, ctx, target_member, action_name, reason, action_func, timeout_sec=300):
        """
        スタッフ投票でアクションを実行する共通メソッド。
        action_func: 可決時に呼ばれるasync関数 (ctx, member, reason)
        """
        import discord, asyncio, datetime
        role = self.get_staff_role()
        staff_members = [m for m in self.guild.members if role in m.roles and not m.bot]
        if len(staff_members) < 2:
            await ctx.send("オンラインのスタッフが2人未満のため投票できません。"); return
        vote_data = {"yes": set(), "no": set(), "done": False}
        start_time = discord.utils.utcnow()
        end_time = start_time + datetime.timedelta(seconds=timeout_sec)
        embed = discord.Embed(
            title=f"🗳️ {action_name}の投票",
            description=f"{target_member.mention} を下記の理由で{action_name}しますか？",
            color=0x3498DB,
        )
        embed.set_thumbnail(url=target_member.display_avatar.url)
        embed.add_field(name="理由", value=reason, inline=False)
        embed.add_field(name="投票期限", value=f"{timeout_sec//60}分", inline=True)
        embed.add_field(
            name="必要数",
            value=f"オンラインスタッフの過半数（{len(staff_members)//2+1}人以上）",
            inline=True,
        )
        embed.set_footer(text="※投票対象はオンラインのスタッフのみ")
        embed.timestamp = discord.utils.utcnow()
        vote_message = await ctx.send(embed=embed)
        class VoteView(discord.ui.View):
            def __init__(self, timeout=timeout_sec):
                super().__init__(timeout=timeout)
            @discord.ui.button(label="賛成", style=discord.ButtonStyle.success, emoji="✅")
            async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
                voter = interaction.user
                if voter not in staff_members:
                    await interaction.response.send_message("スタッフのみ投票できます。", ephemeral=True); return
                if voter.id in vote_data["yes"] or voter.id in vote_data["no"]:
                    await interaction.response.send_message("既に投票済みです。", ephemeral=True); return
                vote_data["yes"].add(voter.id)
                await interaction.response.send_message("賛成票を投じました。", ephemeral=True)
                await update_vote_status()
            @discord.ui.button(label="反対", style=discord.ButtonStyle.danger, emoji="❌")
            async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
                voter = interaction.user
                if voter not in staff_members:
                    await interaction.response.send_message("スタッフのみ投票できます。", ephemeral=True); return
                if voter.id in vote_data["yes"] or voter.id in vote_data["no"]:
                    await interaction.response.send_message("既に投票済みです。", ephemeral=True); return
                vote_data["no"].add(voter.id)
                await interaction.response.send_message("反対票を投じました。", ephemeral=True)
                await update_vote_status()
        async def update_vote_status():
            total = len(staff_members)
            yes = len(vote_data["yes"])
            no = len(vote_data["no"])
            updated_embed = discord.Embed(
                title=f"🗳️ {action_name}の投票",
                description=f"{target_member.mention} を{action_name}する投票進行中",
                color=0x3498DB,
            )
            updated_embed.set_thumbnail(url=target_member.display_avatar.url)
            updated_embed.add_field(name="理由", value=reason, inline=False)
            yes_bar = "🟩" * yes
            no_bar = "🟥" * no
            remaining = "⬜" * (total - yes - no)
            updated_embed.add_field(name="投票状況", value=f"{yes_bar}{no_bar}{remaining}", inline=False)
            updated_embed.add_field(name="賛成", value=f"{yes}票", inline=True)
            updated_embed.add_field(name="反対", value=f"{no}票", inline=True)
            updated_embed.add_field(name="残り", value=f"{total - yes - no}票", inline=True)
            updated_embed.add_field(name="必要数", value=f"{total//2+1}票 (過半数)", inline=True)
            updated_embed.add_field(name="残り時間", value=f"<t:{int(end_time.timestamp())}:R>", inline=True)
            updated_embed.set_footer(text="※投票対象はオンラインのスタッフのみ")
            updated_embed.timestamp = discord.utils.utcnow()
            await vote_message.edit(embed=updated_embed)
            if yes >= (total // 2 + 1):
                vote_data["done"] = True
                result_embed = discord.Embed(
                    title=f"✅ {action_name}投票可決",
                    description=f"{target_member.mention} を{action_name}します。",
                    color=0x2ECC71,
                )
                result_embed.set_thumbnail(url=target_member.display_avatar.url)
                result_embed.add_field(name="理由", value=reason, inline=False)
                result_embed.add_field(
                    name="最終結果",
                    value=f"賛成: {yes}票 / 反対: {no}票 / 必要: {total//2+1}票",
                    inline=False,
                )
                result_embed.set_footer(text="投票は可決されました")
                result_embed.timestamp = discord.utils.utcnow()
                await vote_message.edit(embed=result_embed, view=None)
                try:
                    await action_func(ctx, target_member, reason)
                except Exception:
                    pass
                view.stop()
            elif yes + no == total:
                vote_data["done"] = True
                result_embed = discord.Embed(
                    title=f"❌ {action_name}投票否決",
                    description=f"過半数に達しませんでした。{action_name}は行われません。",
                    color=0xE74C3C,
                )
                result_embed.set_thumbnail(url=target_member.display_avatar.url)
                result_embed.add_field(name="理由", value=reason, inline=False)
                result_embed.add_field(
                    name="最終結果",
                    value=f"賛成: {yes}票 / 反対: {no}票 / 必要: {total//2+1}票",
                    inline=False,
                )
                result_embed.set_footer(text="投票は否決されました")
                result_embed.timestamp = discord.utils.utcnow()
                await vote_message.edit(embed=result_embed, view=None)
                view.stop()
        view = VoteView(timeout=timeout_sec)
        await vote_message.edit(view=view)
        async def timeout_task():
            await asyncio.sleep(timeout_sec)
            if not vote_data["done"]:
                total = len(staff_members)
                yes = len(vote_data["yes"])
                no = len(vote_data["no"])
                timeout_embed = discord.Embed(
                    title=f"⏰ {action_name}投票期限切れ",
                    description=f"投票期限が切れました。{action_name}は行われません。",
                    color=0xF39C12,
                )
                timeout_embed.set_thumbnail(url=target_member.display_avatar.url)
                timeout_embed.add_field(name="理由", value=reason, inline=False)
                timeout_embed.add_field(
                    name="最終結果",
                    value=f"賛成: {yes}票 / 反対: {no}票 / 必要: {total//2+1}票",
                    inline=False,
                )
                timeout_embed.set_footer(text="投票期限切れのため否決されました")
                timeout_embed.timestamp = discord.utils.utcnow()
                await vote_message.edit(embed=timeout_embed, view=None)
                view.stop()
        asyncio.create_task(timeout_task())
