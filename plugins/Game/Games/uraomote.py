# 必要なimport

import discord
import asyncio
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


# --- コイントス（表裏当て）ゲーム ---
from plugins.Game.game import game_manager

def register_game(game_manager):
    game_manager.register_game(
        'cointoss',
        'コイントス3ラウンド（表裏当て）',
        matching=True,
        start_func=start_cointoss,
        min_players=1,
        max_players=2
    )



async def start_cointoss(ctx, players):
    """
    3ラウンドのコイントス表裏当てゲーム。各プレイヤーが毎回表裏を選び、選択ごとにGIFで結果を表示。
    勝ちで10コイン、負けで5コイン。
    """
    n = len(players)
    total_results = []
    win_count = {uid: 0 for uid, _ in players}
    lose_count = {uid: 0 for uid, _ in players}
    msg = None
    for round_num in range(1, 4):
        round_results = []
        for idx, (uid, uname) in enumerate(players):
            # 番の案内
            embed = discord.Embed(title=f"🪙 コイントス Round {round_num}", description=f"{uname}さんの番です。表か裏かを選んでください！", color=0x5865f2)
            view = CoinTossView([(uid, uname)])
            if msg is None:
                msg = await ctx.send(embed=embed, view=view)
            else:
                await msg.edit(embed=embed, view=view)
            try:
                await asyncio.wait_for(view.done.wait(), timeout=30)
            except asyncio.TimeoutError:
                timeout_embed = discord.Embed(title=f"🪙 コイントス Round {round_num}", description=f"⏰ タイムアウト。自動でランダム選択されます。", color=0x5865f2)
                await msg.edit(embed=timeout_embed, view=view)
                view.auto_select()
            # 結果判定
            choice = view.choices.get(str(uid), random.choice(['表', '裏']))
            coin = random.choice(['表', '裏'])
            is_win = (choice == coin)
            if is_win:
                win_count[uid] += 1
            else:
                lose_count[uid] += 1
            result = f"{uname}さんの選択: **{choice}**\nコイントス結果: **{coin}**\n"
            if is_win:
                result += "🟢 勝ち！ +10コイン"
            else:
                result += "🔴 負け +5コイン"
            round_results.append(result)
        # ラウンドごとにまとめてedit
        round_embed = discord.Embed(title=f"🪙 コイントス Round {round_num} 結果", description='\n\n'.join(round_results), color=0x43b581)
        if msg is not None:
            await msg.edit(embed=round_embed, view=None)
        await asyncio.sleep(2)
    # コイン付与
    for uid in win_count:
        if win_count[uid] > 0:
            game_manager.add_currency(str(uid), 10 * win_count[uid])
    for uid in lose_count:
        if lose_count[uid] > 0:
            game_manager.remove_currency(str(uid), 5 * lose_count[uid])
    # 最終リザルト
    summary = []
    for uid, uname in players:
        total = win_count[uid]*10 - lose_count[uid]*5
        summary.append(f"{uname}: {win_count[uid]}勝 {lose_count[uid]}敗  (合計: {total}コイン)" )
    result_embed = discord.Embed(title="🪙 コイントス最終結果", description='\n'.join(summary), color=0x43b581)
    await ctx.send(embed=result_embed)





class CoinTossButton(discord.ui.Button):
    def __init__(self, label, view):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.label_val = label
        self.view_ref = view
    async def callback(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        # 自分の番以外は押せない
        allowed_ids = [str(u[0]) for u in self.view_ref.players]
        if user_id not in allowed_ids:
            await interaction.response.send_message("あなたの番ではありません。", ephemeral=True)
            return
        if user_id in self.view_ref.choices:
            await interaction.response.send_message("すでに選択済みです。", ephemeral=True)
            return
        self.view_ref.choices[user_id] = self.label_val
        await interaction.response.send_message(f"{self.label_val} を選択しました！", ephemeral=True)
        if len(self.view_ref.choices) >= self.view_ref.n:
            self.view_ref.done.set()


class CoinTossView(discord.ui.View):
    def __init__(self, players, timeout=30):
        super().__init__(timeout=timeout)
        self.players = players
        self.n = len(players)
        self.choices = {}
        self.done = asyncio.Event()
        self.add_item(CoinTossButton('表', self))
        self.add_item(CoinTossButton('裏', self))
    async def on_timeout(self):
        self.auto_select()
        self.done.set()
    def auto_select(self):
        for uid, uname in [(str(u[0]), u[1]) for u in self.players]:
            if uid not in self.choices:
                self.choices[uid] = random.choice(['表', '裏'])


