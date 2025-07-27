

import discord
from discord.ext import commands
from plugins import register_command
import asyncio
from DataBase import get_user_data, set_user_data, update_user_data

class GameManager:
    """
    ゲームの登録・一覧・ランキング・通貨管理・マッチング対応・開始関数管理を統一するクラス
    """
    def __init__(self):
        # {game_name: {'description': str, 'ranking': list, 'matching': bool, 'start_func': callable}}
        self.games = {}

    def register_game(self, name, description, matching=False, start_func=None, end_func=None, min_players=1, max_players=1):
        if name not in self.games:
            self.games[name] = {
                'description': description,
                'ranking': [],
                'matching': matching,
                'start_func': start_func,
                'end_func': end_func,
                'min_players': min_players,
                'max_players': max_players
            }
    def get_min_players(self, name):
        return self.games.get(name, {}).get('min_players', 1)
    def get_max_players(self, name):
        return self.games.get(name, {}).get('max_players', 1)
    def get_end_func(self, name):
        return self.games.get(name, {}).get('end_func', None)

    def get_game_list(self):
        return [(name, info['description']) for name, info in self.games.items()]

    def is_matching_supported(self, name):
        return self.games.get(name, {}).get('matching', False)

    def get_start_func(self, name):
        return self.games.get(name, {}).get('start_func', None)


    def add_currency(self, user_id, amount):
        """コインを加算（負の値は無視）。userData['GameData']['coin'] で永続管理"""
        if amount < 0:
            return
        uid = str(user_id)
        data = get_user_data(uid)
        gamedata = data.get('GameData', {})
        coin = gamedata.get('coin', 0)
        coin = max(0, coin + amount)
        gamedata['coin'] = coin
        data['GameData'] = gamedata
        set_user_data(uid, data)

    def remove_currency(self, user_id, amount):
        """コインを減算（残高が足りない場合は0に）。userData['GameData']['coin'] で永続管理"""
        if amount < 0:
            return
        uid = str(user_id)
        data = get_user_data(uid)
        gamedata = data.get('GameData', {})
        coin = gamedata.get('coin', 0)
        coin = max(0, coin - amount)
        gamedata['coin'] = coin
        data['GameData'] = gamedata
        set_user_data(uid, data)

    def set_currency(self, user_id, amount):
        """コイン残高を直接セット（0未満は0）。userData['GameData']['coin'] で永続管理"""
        uid = str(user_id)
        data = get_user_data(uid)
        gamedata = data.get('GameData', {})
        gamedata['coin'] = max(0, amount)
        data['GameData'] = gamedata
        set_user_data(uid, data)

    def get_currency(self, user_id):
        """コイン残高を取得。userData['GameData']['coin'] で永続管理"""
        uid = str(user_id)
        data = get_user_data(uid)
        gamedata = data.get('GameData', {})
        return max(0, gamedata.get('coin', 0))

    def update_ranking(self, game_name, user_id, score):
        if game_name in self.games:
            ranking = self.games[game_name]['ranking']
            ranking.append({'user_id': user_id, 'score': score})
            ranking.sort(key=lambda x: x['score'], reverse=True)
            self.games[game_name]['ranking'] = ranking[:10]  # 上位10名のみ保持

    def get_ranking(self, game_name):
        if game_name in self.games:
            return self.games[game_name]['ranking']
        return []



import importlib
import os
import sys

game_manager = GameManager()

def register_all_games():
    """
    Game/Games配下の.pyを動的importし、各ファイルでregister_game関数を呼び出してもらう
    """
    # プロジェクトルートをsys.pathに追加
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    games_dir = os.path.join(os.path.dirname(__file__), 'Games')
    for fname in os.listdir(games_dir):
        if fname.endswith('.py') and not fname.startswith('_'):
            modname = f"plugins.Game.Games.{fname[:-3]}"
            try:
                mod = importlib.import_module(modname)
                if hasattr(mod, 'register_game'):
                    mod.register_game(game_manager)
            except Exception as e:
                print(f"[GameLoader] {modname} import error: {e}")

register_all_games()


@commands.command()
async def game(ctx, subcommand=None, *args):
    """
    ゲーム機能のベースコマンドです。
    #game list でゲーム一覧を表示
    #game play <game名> でゲームを開始
    """
    if subcommand == "list":
        games = game_manager.get_game_list()
        if not games:
            await ctx.reply('🎮 登録されているゲームはありません。')
            return
        embed = ctx.bot.Embed(
            title="🎮 ゲーム一覧",
            description="利用可能なゲームのリストです。",
            color=0x5865f2
        ) if hasattr(ctx.bot, 'Embed') else None
        desc = ""
        for name, description in games:
            desc += f"**{name}**: {description}\n"
        if embed:
            embed.description = desc
            await ctx.reply(embed=embed)
        else:
            await ctx.reply(desc)
    elif subcommand == "play":
        if not args:
            await ctx.reply('🎮 遊びたいゲーム名を指定してください。例: `#game play sample`')
            return
        game_name = args[0]
        num_players = 1
        # 2つ目の引数が数字なら人数として扱う
        if len(args) > 1 and str(args[1]).isdigit():
            num_players = int(args[1])
        if game_name not in game_manager.games:
            await ctx.reply(f'❌ `{game_name}` というゲームは登録されていません。')
            return
        # マッチング対応ゲームの場合、min/max_playersを取得
        start_func = game_manager.get_start_func(game_name)
        min_players = game_manager.get_min_players(game_name)
        max_players = game_manager.get_max_players(game_name)
        # 人数指定がmin/max範囲外ならエラー
        if num_players < min_players or num_players > max_players:
            await ctx.reply(f'❌ `{game_name}` のプレイ人数は{min_players}～{max_players}人です。')
            return
        if num_players > 1:
            # マッチング対応ゲームのみ許可
            if not game_manager.is_matching_supported(game_name):
                await ctx.reply(f'❌ `{game_name}` はマルチプレイ・マッチングに対応していません。')
                return
            if start_func:
                embed = ctx.bot.Embed(
                    title=f"🎮 {game_name} マルチプレイマッチング",
                    description=f"{num_players}人マッチング待機中...\n参加したい方はこのメッセージにリアクションしてください！",
                    color=0x43b581
                ) if hasattr(ctx.bot, 'Embed') else None
                msg = await ctx.reply(embed=embed) if embed else await ctx.reply(f'🎮 {game_name} マルチプレイ: {num_players}人マッチング待機中...\n参加したい方はこのメッセージにリアクションしてください！')
                # botが先に✅リアクションを付与
                try:
                    await msg.add_reaction("✅")
                except Exception:
                    pass
                def check(reaction, user):
                    return reaction.message.id == msg.id and str(reaction.emoji) == "✅" and not user.bot
                players = [(ctx.author.id, ctx.author.display_name)]
                started = False
                class StartButtonView(discord.ui.View):
                    def __init__(self, players):
                        super().__init__(timeout=60)
                        self.players = players
                        self.started = False
                    @discord.ui.button(label="開始", style=discord.ButtonStyle.success)
                    async def start_button(self, interaction, button):
                        if not self.started:
                            self.started = True
                            for item in self.children:
                                if isinstance(item, discord.ui.Button):
                                    item.disabled = True
                            await interaction.response.edit_message(view=self)
                            await ctx.send("ゲームを開始します…")
                            await start_func(ctx, self.players)
                try:
                    while len(players) < num_players:
                        reaction, user = await ctx.bot.wait_for('reaction_add', timeout=60.0, check=check)
                        if user.id not in [uid for uid, _ in players]:
                            players.append((user.id, user.display_name))
                            await ctx.send(f"✅ {user.display_name} さんが参加しました！（{len(players)}/{num_players}）")
                        # 最低人数に達したら開始ボタンを表示
                        if len(players) == min_players:
                            if embed:
                                view = StartButtonView(players)
                                await msg.edit(view=view)
                    # 1P, 2P, ... の役割を付与
                    numbered_players = []
                    for i, (uid, uname) in enumerate(players):
                        numbered_players.append((uid, f"{i+1}P:{uname}"))
                    await ctx.send("全員揃いました！ゲームを開始します…")
                    await start_func(ctx, numbered_players)
                except asyncio.TimeoutError:
                    await ctx.send('⏰ マッチングがタイムアウトしました。')
            else:
                await ctx.reply(f'❌ `{game_name}` の開始関数が登録されていません。')
        else:
            # ソロプレイ
            start_func = game_manager.get_start_func(game_name)
            if start_func:
                await start_func(ctx, [(ctx.author.id, "1P:" + ctx.author.display_name)])
            else:
                pass
    elif subcommand == "coin":
        # 通貨システム: 自分の所持コインを表示
        user_id = str(ctx.author.id)
        coin = game_manager.get_currency(user_id)
        await ctx.reply(f'💰 あなたの所持コイン: {coin} コイン')
    else:
        await ctx.reply('🎮 ゲーム機能のベースコマンドです。\n`#game list` でゲーム一覧を表示できます。\n`#game play <ゲーム名>` で遊べます。\n`#game coin` で所持コインを確認できます。')

def setup(bot):
    register_command(bot, game)
