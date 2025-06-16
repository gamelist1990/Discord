from discord.ext import commands
from plugins import register_command
import discord


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

    def is_admin_user(self):
        from index import is_admin, load_config
        config = load_config()
        return is_admin(self.ctx.author.id, self.guild.id, config)

    def is_staff(self):
        role = self.get_staff_role()
        return bool(role and role in self.ctx.author.roles)

    def get_staff_members(self):
        role = self.get_staff_role()
        if not role:
            return []
        return [m for m in self.guild.members if role in m.roles and not m.bot]

    async def send_staff_alert(self, message):
        from DataBase import get_guild_value
        alert_channel_id = get_guild_value(self.guild.id, "alertChannel")
        if alert_channel_id:
            channel = self.guild.get_channel(int(alert_channel_id))
            if channel:
                await channel.send(message)

    async def vote_action(self, ctx, target_member, action_name, reason, action_func, timeout_sec=300):
        """
        スタッフ投票でアクションを実行する共通メソッド。
        action_func: 可決時に呼ばれるasync関数 (ctx, member, reason)
        """
        role = self.get_staff_role()
        staff_members = [m for m in self.guild.members if role in m.roles and not m.bot]
        if len(staff_members) < 2:
            await ctx.send('スタッフが2人未満のため投票できません。')
            return
        vote_data = {'yes': set(), 'no': set(), 'done': False}
        vote_message = await ctx.send(f"{target_member.mention} を理由:『{reason}』で{action_name}しますか？\nスタッフの過半数が{timeout_sec//60}分以内に可決で実行されます。\n投票はボタンで行われます。")
        class VoteView(discord.ui.View):
            def __init__(self, timeout=timeout_sec):
                super().__init__(timeout=timeout)
            @discord.ui.button(label="賛成", style=discord.ButtonStyle.success)
            async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
                voter = interaction.user
                if voter not in staff_members:
                    await interaction.response.send_message("スタッフのみ投票できます。", ephemeral=True)
                    return
                if voter.id in vote_data['yes'] or voter.id in vote_data['no']:
                    await interaction.response.send_message("既に投票済みです。", ephemeral=True)
                    return
                vote_data['yes'].add(voter.id)
                await interaction.response.send_message("賛成票を投じました。", ephemeral=True)
                await update_vote_status()
            @discord.ui.button(label="反対", style=discord.ButtonStyle.danger)
            async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
                voter = interaction.user
                if voter not in staff_members:
                    await interaction.response.send_message("スタッフのみ投票できます。", ephemeral=True)
                    return
                if voter.id in vote_data['yes'] or voter.id in vote_data['no']:
                    await interaction.response.send_message("既に投票済みです。", ephemeral=True)
                    return
                vote_data['no'].add(voter.id)
                await interaction.response.send_message("反対票を投じました。", ephemeral=True)
                await update_vote_status()
        async def update_vote_status():
            total = len(staff_members)
            yes = len(vote_data['yes'])
            no = len(vote_data['no'])
            await vote_message.edit(content=f"{target_member.mention} {action_name}投票中: 賛成 {yes} / 反対 {no} / 必要: {total//2+1} ({timeout_sec//60}分以内)")
            if yes >= (total // 2 + 1):
                vote_data['done'] = True
                await vote_message.edit(content=f"可決: {target_member.mention} を{action_name}します。", view=None)
                try:
                    await action_func(ctx, target_member, reason)
                    await self.send_staff_alert(f"{target_member.mention} をスタッフ投票で{action_name}しました。理由: {reason}")
                except Exception:
                    await ctx.send(f"{target_member.mention} の{action_name}に失敗しました。Botの権限を確認してください。")
                view.stop()
            elif yes + no == total:
                vote_data['done'] = True
                await vote_message.edit(content=f"否決: 過半数に達しませんでした。{action_name}は行われません。", view=None)
                view.stop()
        view = VoteView(timeout=timeout_sec)
        await vote_message.edit(view=view)
        async def timeout_task():
            import asyncio
            await asyncio.sleep(timeout_sec)
            if not vote_data['done']:
                await vote_message.edit(content=f"投票期限切れ: 過半数に達しませんでした。{action_name}は行われません。", view=None)
                view.stop()
        import asyncio
        asyncio.create_task(timeout_task())

def setup(bot):
    @commands.group()
    async def staff(ctx):
        """
        スタッフ関連のコマンドグループ。
        サブコマンドが指定されていない場合は案内メッセージを表示。
        スタッフ以外は利用不可。
        """
        util = StaffUtil(ctx)
        if not util.is_staff() and not util.is_admin_user():
            await ctx.send('このコマンドはスタッフ専用です。')
            return
        if ctx.invoked_subcommand is None:
            await ctx.send('staff help などのサブコマンドを指定してください')

    @staff.command(name='role')
    async def role_cmd(ctx, role_id: int):
        """
        指定ロールIDをスタッフロールとして設定します（管理者のみ）。
        使い方: #staff role <roleID>
        """
        util = StaffUtil(ctx)
        from DataBase import update_guild_data
        if not util.is_admin_user():
            await ctx.send('このコマンドは管理者専用です。')
            return
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        if not role:
            await ctx.send('指定したロールIDのロールが見つかりません。')
            return
        update_guild_data(ctx.guild.id, "staffRole", str(role_id))
        await ctx.send(f'スタッフロールを {role.mention} に設定しました。')

    @staff.command(name='alert')
    async def alert_cmd(ctx, channel_id_or_none: str):
        """
        スタッフ通知用チャンネルを設定/解除します（管理者専用）。
        使い方: #staff alert <チャンネルID|none>
        """
        util = StaffUtil(ctx)
        from DataBase import update_guild_data
        if not util.is_admin_user():
            await ctx.send('このコマンドは管理者専用です。')
            return
        if channel_id_or_none.lower() == 'none':
            update_guild_data(ctx.guild.id, "alertChannel", None)
            await ctx.send('通知チャンネル設定を解除しました。')
            return
        try:
            channel_id = int(channel_id_or_none)
            channel = ctx.guild.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                await ctx.send('指定したチャンネルIDのテキストチャンネルが見つかりません。')
                return
            update_guild_data(ctx.guild.id, "alertChannel", str(channel_id))
            await ctx.send(f'通知チャンネルを {channel.mention} に設定しました。')
        except Exception:
            await ctx.send('チャンネルIDが不正です。')

    @staff.command(name='help')
    async def help_cmd(ctx):
        """
        staffコマンドの使い方を表示します。
        使い方: #staff help
        """
        help_text = (
            "【#staff コマンド一覧】\n"
            "#staff help - このヘルプを表示\n"
            "#staff list - スタッフ一覧を表示\n"
            "#staff role <roleID> - スタッフロールを設定（管理者のみ）\n"
            "#staff alert <チャンネルID|none> - スタッフ通知チャンネルを設定/解除（管理者のみ）\n"
            "#staff timeout @ユーザー <秒数> - スタッフ以外のユーザーにタイムアウトを付与\n"
        )
        await ctx.send(help_text)

    @staff.command(name='list')
    async def list_cmd(ctx):
        """
        スタッフ一覧を表示します。
        使い方: #staff list
        """
        util = StaffUtil(ctx)
        role = util.get_staff_role()
        if not role:
            await ctx.send('スタッフロールが設定されていません。')
            return
        members = [m.mention for m in ctx.guild.members if role in m.roles]
        if not members:
            await ctx.send('スタッフロールを持つメンバーはいません。')
            return
        await ctx.send('スタッフ一覧:\n' + '\n'.join(members))

    @staff.command(name='private')
    async def private_cmd(ctx):
        """
        スタッフ専用のプライベートカテゴリとチャンネルを作成します（管理者のみ）。
        使い方: #staff private
        """
        util = StaffUtil(ctx)
        if not util.is_admin_user():
            await ctx.send('このコマンドは管理者専用です。')
            return
        guild = ctx.guild
        category_name = "🛡️スタッフ専用"
        channel_name = "staff-chat"
        category = discord.utils.get(guild.categories, name=category_name)
        role = util.get_staff_role()
        if not role:
            await ctx.send('スタッフロールが設定されていません。')
            return
        if not category:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            category = await guild.create_category(category_name, overwrites=overwrites)
            await ctx.send(f"カテゴリ {category_name} を作成しました。")
        else:
            await ctx.send(f"カテゴリ {category_name} は既に存在します。")
        channel = discord.utils.get(category.text_channels, name=channel_name) if category else None
        if not channel:
            channel = await guild.create_text_channel(channel_name, category=category)
            await ctx.send(f"チャンネル {channel.mention} を作成しました。")
        else:
            await ctx.send(f"チャンネル {channel.mention} は既に存在します。")

    @staff.command(name='timeout')
    async def timeout_cmd(ctx, member: discord.Member, seconds: int):
        """
        スタッフ以外の指定ユーザーに指定秒数のタイムアウトを付与し、通知チャンネルが設定されていれば通知も送信。
        使い方: #staff timeout @ユーザー <秒数>
        """
        util = StaffUtil(ctx)
        role = util.get_staff_role()
        if not role:
            await ctx.send('スタッフロールが設定されていません。')
            return
        if role in member.roles:
            await ctx.send(f'{member.mention} はスタッフロールを持っているためタイムアウトできません。')
            return
        if member.bot:
            await ctx.send('Botにはタイムアウトできません。')
            return
        import datetime
        until = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
        try:
            await member.edit(timed_out_until=until)
            msg = f"{member.mention} に {seconds}秒のタイムアウトを付与しました。"
            await ctx.send(msg)
            await util.send_staff_alert(msg)
        except Exception:
            await ctx.send(f'{member.mention} へのタイムアウト付与に失敗しました。')

    @staff.command(name='kick')
    async def kick_cmd(ctx, member: discord.Member, *, reason: str):
        """
        スタッフの過半数投票で指定ユーザーをキック。投票は5分間有効。
        使い方: #staff kick @ユーザー 理由
        """
        util = StaffUtil(ctx)
        role = util.get_staff_role()
        if not role:
            await ctx.send('スタッフロールが設定されていません。')
            return
        if role in member.roles:
            await ctx.send('スタッフはキックできません。')
            return
        if member.bot:
            await ctx.send('Botはキックできません。')
            return
        async def do_kick(ctx, member, reason):
            await member.kick(reason=f"スタッフ投票により可決: {reason}")
        await util.vote_action(ctx, member, "キック", reason, do_kick, timeout_sec=300)

    register_command(bot, staff)
