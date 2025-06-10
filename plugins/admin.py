from discord.ext import commands
from plugins import register_command
from index import save_config, load_config

# サーバー管理者をguildAdminsに追加するコマンド

def setup(bot):
    @commands.group()
    async def admin(ctx):
        """
        管理者関連のコマンドグループ。
        サブコマンドが指定されていない場合は案内メッセージを表示。
        """
        if ctx.invoked_subcommand is None:
            await ctx.send('admin add server などのサブコマンドを指定してください')

    @admin.command(name='add')
    async def add(ctx, target: str):
        """
        サーバー内の管理者権限ユーザーを自動的にguildAdminsへ登録します。
        使い方: #admin add server
        """
        if target != 'server':
            await ctx.send('現在サポートされているのは admin add server のみです')
            return
        config = load_config()
        guild = ctx.guild
        if not guild:
            await ctx.send('このコマンドはサーバー内でのみ使用できます')
            return
        # 管理者ロールを持つユーザーを抽出（botは除外）
        admin_ids = [str(m.id) for m in guild.members if any(r.permissions.administrator for r in m.roles) and not m.bot]
        if not admin_ids:
            await ctx.send('管理者権限を持つユーザーが見つかりませんでした')
            return
        # guildAdminsに登録
        if 'guildAdmins' not in config:
            config['guildAdmins'] = {}
        config['guildAdmins'][str(guild.id)] = admin_ids
        save_config(config)
        # Embedで見やすく表示
        from discord import Embed
        lines = []
        for m in guild.members:
            if str(m.id) in admin_ids:
                lines.append(f"- {m.mention} (`{m.id}`)")
        desc = '\n'.join(lines) if lines else '（該当ユーザーなし）'
        embed = Embed(title="管理者権限ユーザーを登録しました", description=desc, color=0x4ade80)
        embed.set_footer(text=f"合計: {len(admin_ids)}名")
        await ctx.send(embed=embed)

    # コマンドをBotに登録
    register_command(bot, admin, aliases=None, admin=True)
