from discord.ext import commands
from plugins import register_command
import discord
from index import is_admin, load_config

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
        from index import is_admin
        config = load_config()
        return is_admin(self.ctx.author.id, self.guild.id, config)

    async def is_staff(self):
        role = self.get_staff_role()
        return bool(role and role in self.ctx.author.roles)

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
            # 通知チャンネルが存在し、かつコマンド実行チャンネルと異なる場合のみ送信
            if channel and channel.id != self.ctx.channel.id:
                if embed:
                    await channel.send(content=message if message else None, embed=embed)
                else:
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

    @staticmethod
    async def handle_role_cmd(ctx, role_id: int):
        """
        指定ロールIDをスタッフロールとして設定します（管理者のみ）。
        使い方: #staff role <roleID>
        """
        util = StaffUtil(ctx)
        from DataBase import update_guild_data
        if not (await util.is_admin_user()):
            await ctx.send('このコマンドは管理者専用です。')
            return
        role = discord.utils.get(ctx.guild.roles, id=role_id)
        if not role:
            await ctx.send('指定したロールIDのロールが見つかりません。')
            return
        update_guild_data(ctx.guild.id, "staffRole", str(role_id))
        await ctx.send(f'スタッフロールを {role.mention} に設定しました。')

    @staticmethod
    async def handle_alert_cmd(ctx, channel_id_or_none: str):
        """
        スタッフ通知用チャンネルを設定/解除します（管理者専用）。
        使い方: #staff alert <チャンネルID|none>
        """
        util = StaffUtil(ctx)
        from DataBase import update_guild_data
        if not (await util.is_admin_user()):
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

    @staticmethod
    async def handle_help_cmd(ctx):
        """
        staffコマンドの使い方を表示します。
        使い方: #staff help
        """
        embed = discord.Embed(
            title="📋 スタッフコマンド一覧",
            description="スタッフ管理用コマンドの使い方",
            color=0x3498db  # 青色
        )
        
        # 一般コマンド
        embed.add_field(
            name="🔍 一般コマンド", 
            value="```\n#staff help - このヘルプを表示\n#staff list - スタッフ一覧を表示\n```", 
            inline=False
        )
        
        # 管理コマンド
        embed.add_field(
            name="⚙️ 管理コマンド（管理者専用）", 
            value="```\n#staff role <roleID> - スタッフロールを設定\n#staff alert <チャンネルID|none> - スタッフ通知チャンネルを設定/解除\n#staff private - スタッフ専用カテゴリとチャンネルを作成\n```", 
            inline=False
        )
        
        # 操作コマンド
        embed.add_field(
            name="🛡️ 操作コマンド（スタッフのみ）",
            value="""```
#staff timeout @ユーザー <秒数> [理由] - スタッフ以外のユーザーにタイムアウトを付与
#staff kick @ユーザー <理由> - スタッフまたは管理者が実行可能。スタッフ投票で過半数賛成でユーザーをキック
```""",
            inline=False
        )
        
        embed.set_footer(text="詳細は各コマンドのヘルプを参照してください。")
        
        await ctx.send(embed=embed)

    @staticmethod
    async def handle_list_cmd(ctx):
        """
        スタッフ一覧を表示します。
        使い方: #staff list
        """
        util = StaffUtil(ctx)
        role = util.get_staff_role()
        
        embed = discord.Embed(
            title="👥 スタッフ一覧",
            color=0x2ecc71  # 緑色
        )
        
        if not role:
            if await util.is_admin_user():
                embed.description = "現在スタッフはいません"
                embed.set_footer(text="スタッフロールが設定されていません")
                await ctx.send(embed=embed)
                return
            else:
                await ctx.send('スタッフロールを持つメンバーはいません。')
                return
                
        # メンションではなく名前で表示する
        staff_members = [m for m in ctx.guild.members if role in m.roles and not m.bot]
        if not staff_members:
            embed.description = "現在スタッフはいません"
            await ctx.send(embed=embed)
            return
        
        # スタッフ名を表示名でリスト化
        staff_names = [f"• {m.display_name}" for m in staff_members]
        
        # リストを1つのフィールドに表示
        embed.description = "\n".join(staff_names)
        embed.set_footer(text=f"スタッフロール: {role.name} • 合計: {len(staff_members)}名")
        await ctx.send(embed=embed)

    @staticmethod
    async def handle_private_cmd(ctx):
        """
        スタッフ専用のプライベートカテゴリとチャンネルを作成します（管理者のみ）。
        使い方: #staff private
        """
        util = StaffUtil(ctx)
        if not (await util.is_admin_user()):
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
        if unit == 's' or unit == '':
            return value
        elif unit == 'm':
            return value * 60
        elif unit == 'h':
            return value * 3600
        elif unit == 'd':
            return value * 86400
        else:
            raise ValueError("不正な時間単位です")

    @staticmethod
    async def handle_timeout_cmd(ctx, member_or_id, seconds_str, *, reason=None):
        """
        スタッフ以外の指定ユーザーに指定秒数のタイムアウトを付与し、通知チャンネルが設定されていれば通知も送信。
        使い方: #staff timeout @ユーザー <秒数> [理由]
               #staff timeout ユーザーID <秒数> [理由]
               #staff timeout @ユーザー 1h 荒らし行為のため
        """
        util = StaffUtil(ctx)
        role = util.get_staff_role()
        if not role:
            await ctx.send('スタッフロールが設定されていません。')
            return
        # ユーザーID対応
        member = member_or_id
        try:
            # 通常の数字IDの場合
            if isinstance(member_or_id, str) and member_or_id.isdigit():
                member = await ctx.guild.fetch_member(int(member_or_id))
            # メンション形式 <@123456789> の場合
            elif isinstance(member_or_id, str) and member_or_id.startswith('<@') and member_or_id.endswith('>'):
                import re
                # メンションからIDを抽出 (<@123456789> または <@!123456789>)
                mention_match = re.match(r'<@!?(\d+)>', member_or_id)
                if mention_match:
                    user_id = int(mention_match.group(1))
                    member = await ctx.guild.fetch_member(user_id)
                    print(f"[DEBUG] メンションからIDを抽出: {member_or_id} → {user_id}")
                else:
                    await ctx.send(f'無効なメンション形式です: {member_or_id}')
                    return
        except discord.NotFound:
            await ctx.send(f'ID: {member_or_id} のユーザーが見つかりません。')
            return
        except Exception as e:
            await ctx.send(f'エラーが発生しました: {str(e)}')
            return
            
        # メンバーオブジェクトかどうか確認
        if not isinstance(member, discord.Member):
            await ctx.send(f'無効なユーザーです。メンションまたはIDで指定してください。')
            return
            
        if role in member.roles:
            await ctx.send(f'{member.mention} はスタッフロールを持っているためタイムアウトできません。')
            return
        if member.bot:
            await ctx.send('Botにはタイムアウトできません。')
            return
        try:
            seconds = StaffUtil.parse_timestr(seconds_str)
        except Exception as e:
            await ctx.send(f'時間指定が不正です: {e}')
            return
        import datetime
        until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
        try:
            # 理由がある場合はタイムアウト理由に設定
            timeout_reason = f"スタッフによるタイムアウト: {reason}" if reason else "スタッフによるタイムアウト"
            
            # デバッグ出力
            print(f"[DEBUG] タイムアウト実行: member={member.id}, seconds={seconds}, reason={reason}")
            
            try:
                await member.edit(timed_out_until=until, reason=timeout_reason)
            except discord.Forbidden:
                await ctx.send(f"⚠️ 権限不足のためタイムアウトできませんでした。Botの権限を確認してください。")
                return
            except discord.HTTPException as http_e:
                await ctx.send(f"⚠️ Discordサーバーエラー: {http_e}")
                return
            except Exception as other_e:
                await ctx.send(f"⚠️ 予期せぬエラー: {other_e}")
                return
                
            # Embedを使用した通知に変更
            embed = discord.Embed(
                title="タイムアウト通知",
                description=f"{member.mention} に {seconds}秒のタイムアウトを付与しました。",
                color=0xf1c40f  # 黄色
            )
            embed.set_author(name=f"{ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="期間", value=f"{seconds}秒", inline=True)
            embed.add_field(name="終了時刻", value=f"<t:{int(until.timestamp())}:F>", inline=True)
            # 理由がある場合は表示
            if reason:
                embed.add_field(name="理由", value=reason, inline=False)
            embed.timestamp = datetime.datetime.now()
            
            await ctx.send(embed=embed)
            # 通知チャンネルにも同じEmbedを送信（コマンド実行チャンネルと異なる場合のみ）
            await util.send_staff_alert(None, embed=embed)
        except Exception as e:
            error_message = f'{member.mention} へのタイムアウト付与に失敗しました。'
            
            # エラーの詳細を追加
            if hasattr(member, 'guild_permissions') and member.guild_permissions.administrator:
                error_message += "\n⚠️ 管理者権限を持つメンバーはタイムアウトできません。"
            elif hasattr(ctx.guild, 'owner') and member.id == ctx.guild.owner.id:
                error_message += "\n⚠️ サーバーオーナーはタイムアウトできません。"
            elif hasattr(ctx.guild, 'me') and member.top_role >= ctx.guild.me.top_role:
                error_message += "\n⚠️ Botより上位のロールを持つメンバーはタイムアウトできません。"
            else:
                error_message += f"\nエラー詳細: {str(e)}"
                
            await ctx.send(error_message)

    @staticmethod
    async def handle_kick_cmd(ctx, member, reason: str):
        """
        スタッフの過半数投票で指定ユーザーをキック。投票は5分間有効。
        使い方: #staff kick @ユーザー 理由
               #staff kick ユーザーID 理由
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

def setup(bot):
    @commands.group()
    async def staff(ctx):
        util = StaffUtil(ctx)
        if ctx.invoked_subcommand is None:
            await ctx.send('staff help などのサブコマンドを指定してください')
            return
        subcmd = ctx.invoked_subcommand.name if ctx.invoked_subcommand else None
        admin_only = {'role', 'alert', 'private'}
        # help以外、かつ管理者専用以外はスタッフまたは管理者のみ許可
        if subcmd not in ('help', *admin_only) and not (await util.is_staff()) and not (await util.is_admin_user()):
            await ctx.send('このコマンドはスタッフ専用です。')
            return
        # スタッフロール未設定時は一度だけ案内（help, admin専用コマンドは除外）
        if subcmd not in ('help', *admin_only) and not util.get_staff_role():
            await ctx.send('スタッフロールが設定されていません。')
            return

    @staff.command(name='role')
    async def role_cmd(ctx, role_id: int):
        await StaffUtil.handle_role_cmd(ctx, role_id)

    @staff.command(name='alert')
    async def alert_cmd(ctx, channel_id_or_none: str):
        await StaffUtil.handle_alert_cmd(ctx, channel_id_or_none)

    @staff.command(name='help')
    async def help_cmd(ctx):
        await StaffUtil.handle_help_cmd(ctx)

    @staff.command(name='list')
    async def list_cmd(ctx):
        await StaffUtil.handle_list_cmd(ctx)

    @staff.command(name='private')
    async def private_cmd(ctx):
        await StaffUtil.handle_private_cmd(ctx)

    @staff.command(name='timeout')
    async def timeout_cmd(ctx, member_or_id, seconds_str, *, reason=None):
        """
        タイムアウトコマンド: @ユーザー または ユーザーID で指定可能。時間は 1s, 1m, 2h, 1d など対応
        使い方: #staff timeout @ユーザー 1h [理由] または #staff timeout ユーザーID 30m [理由]
        メンション例: #staff timeout <@123456789> 10m 迷惑行為
        """
        await StaffUtil.handle_timeout_cmd(ctx, member_or_id, seconds_str, reason=reason)

    @staff.command(name='kick')
    async def kick_cmd(ctx, member_or_id, *, reason: str):
        """
        スタッフ投票でユーザーをキック
        使い方: #staff kick @ユーザー 理由
               #staff kick ユーザーID 理由
        """
        # ユーザーIDが渡された場合は Member オブジェクトに変換
        member = member_or_id
        try:
            if isinstance(member_or_id, str) and member_or_id.isdigit():
                member = await ctx.guild.fetch_member(int(member_or_id))
        except discord.NotFound:
            await ctx.send(f'ID: {member_or_id} のユーザーが見つかりません。')
            return
        except Exception as e:
            await ctx.send(f'エラーが発生しました: {str(e)}')
            return
        
        await StaffUtil.handle_kick_cmd(ctx, member, reason)

    register_command(bot, staff)
