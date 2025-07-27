import discord
import asyncio
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# --- APIクラス ---
class RPGAPI:

    def __init__(self):
        # マップ定義: 0=道, 1=壁, 2=王城, 3=勇者の家, 4=ショップ
        self.width = 7
        self.height = 7
        self.map = [
            [3,0,0,0,0,0,0],
            [1,1,1,0,1,1,0],
            [0,0,0,0,0,1,0],
            [0,1,1,1,0,1,0],
            [0,1,2,0,0,0,0],
            [0,1,1,1,1,1,0],
            [0,0,0,0,4,0,0],
        ]
        self.player_pos = [0, 0]  # 勇者の家
        self.money = 100  # 初期所持金
        self.quest_state = 0  # 0:未受注, 1:受注, 2:クリア
        self.in_battle = False
        self.battle_state = None
        self.inventory = []
        self.shop_items = [
            {"name": "やくそう", "price": 20, "desc": "HPを10回復"},
            {"name": "つるぎ", "price": 50, "desc": "攻撃力+5"},
        ]
        self.has_sword = False

    def get_cell_type(self, x, y):
        v = self.map[y][x]
        if v == 0: return 'road'
        if v == 1: return 'wall'
        if v == 2: return 'castle'
        if v == 3: return 'home'
        if v == 4: return 'shop'
        return 'unknown'

    def move(self, direction):
        dx, dy = 0, 0
        if direction == 'up': dy = -1
        elif direction == 'down': dy = 1
        elif direction == 'left': dx = -1
        elif direction == 'right': dx = 1
        nx, ny = self.player_pos[0] + dx, self.player_pos[1] + dy
        if 0 <= nx < self.width and 0 <= ny < self.height and self.map[ny][nx] != 1:
            self.player_pos = [nx, ny]
        cell = self.get_cell_type(*self.player_pos)
        return self.player_pos, cell

    def draw_map(self):
        w, h = 350, 350
        cell = w // self.width
        img = Image.new("RGB", (w, h), (255,255,255))
        draw = ImageDraw.Draw(img)
        for y in range(self.height):
            for x in range(self.width):
                v = self.map[y][x]
                if v == 1:
                    color = (120,120,120)
                elif v == 2:
                    color = (255,220,0)
                elif v == 3:
                    color = (0,255,180)
                elif v == 4:
                    color = (255,100,200)
                else:
                    color = (255,255,255)
                draw.rectangle([x*cell, y*cell, (x+1)*cell, (y+1)*cell], fill=color, outline=(0,0,0))
        # プレイヤー
        px, py = self.player_pos
        draw.ellipse([px*cell+8, py*cell+8, (px+1)*cell-8, (py+1)*cell-8], fill=(0,128,255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def get_status_text(self):
        cell = self.get_cell_type(*self.player_pos)
        loc = {'home':'勇者の家', 'castle':'王城', 'shop':'ショップ', 'road':'道', 'unknown':'?'}[cell]
        quest = ['未受注','受注中','クリア'][self.quest_state]
        inv = ', '.join(self.inventory) if self.inventory else 'なし'
        return f"場所: {loc}\n所持金: {self.money}en\nクエスト: {quest}\n持ち物: {inv}"

    # ショップAPI
    def can_shop(self):
        return self.get_cell_type(*self.player_pos) == 'shop'
    def buy_item(self, item_idx):
        if not self.can_shop():
            return False, "ここでは買い物できません。"
        if not (0 <= item_idx < len(self.shop_items)):
            return False, "その商品はありません。"
        item = self.shop_items[item_idx]
        if self.money >= item["price"]:
            self.money -= item["price"]
            self.inventory.append(item["name"])
            if item["name"] == "つるぎ":
                self.has_sword = True
            return True, f'{item["name"]} を購入した！'
        return False, "お金が足りません。"

    # クエストAPI
    def can_quest(self):
        return self.get_cell_type(*self.player_pos) == 'castle' and self.quest_state == 0
    def accept_quest(self):
        if self.can_quest():
            self.quest_state = 1
            return True, "クエストを受注した！"
        return False, "今はクエストを受けられません。"
    def complete_quest(self):
        if self.quest_state == 1 and self.get_cell_type(*self.player_pos) == 'castle':
            self.quest_state = 2
            self.money += 100
            return True, "クエストクリア！ご褒美100enを獲得"
        return False, "クエストをクリアできません。"

    # バトルAPI
    def start_battle(self):
        self.in_battle = True
        self.battle_state = {'player_hp': 30, 'enemy_hp': 20, 'turn': 'player'}

    def battle_turn(self, action):
        if not self.in_battle or not self.battle_state:
            return ["バトル中ではありません。"], self.battle_state if self.battle_state else {}
        s = self.battle_state
        log = []
        # プレイヤーターン
        if s.get('turn') == 'player':
            if action == 'attack':
                base = 10 if self.has_sword else 5
                dmg = random.randint(base, base+5)
                s['enemy_hp'] -= dmg
                log.append(f'勇者の攻撃! 敵に{dmg}ダメージ')
            elif action == 'heal':
                if "やくそう" in self.inventory:
                    s['player_hp'] += 10
                    self.inventory.remove("やくそう")
                    log.append('やくそうでHPを10回復!')
                else:
                    log.append('やくそうを持っていない!')
            elif action == 'item':
                # アイテムはUIで処理
                pass
            s['turn'] = 'enemy'
        # 敵ターン
        elif s.get('turn') == 'enemy':
            dmg = random.randint(3, 8)
            s['player_hp'] -= dmg
            log.append(f'敵の攻撃! 勇者に{dmg}ダメージ')
            s['turn'] = 'player'
        # 勝敗判定
        if s['enemy_hp'] <= 0:
            self.in_battle = False
            log.append('敵を倒した!')
        elif s['player_hp'] <= 0:
            self.in_battle = False
            log.append('勇者は倒れた…')
        return log, dict(s)

    def generate_maze(self, w, h):
        # シンプルな迷路生成（壁:1, 通路:0, ゴール:2）
        maze = [[0 for _ in range(w)] for _ in range(h)]
        for y in range(h):
            for x in range(w):
                if (x, y) == (w-1, h-1):
                    maze[y][x] = 2  # ゴール
                elif random.random() < 0.2 and (x, y) != (0, 0):
                    maze[y][x] = 1  # 壁
        maze[0][0] = 0  # スタート
        return maze

    # 2重定義を削除（上のmove/draw_mapのみ使用）

# --- Discord UI ---
class MazeButton(discord.ui.Button):
    def __init__(self, label, direction, view):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.direction = direction
        self.view_ref = view
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.view_ref.user_id:
            await interaction.response.send_message("あなたの操作権限がありません。", ephemeral=True)
            return
        pos, cell = self.view_ref.api.move(self.direction)
        img = self.view_ref.api.draw_map()
        file = discord.File(img, filename="maze.png")
        embed = discord.Embed(title="🗺️ 本格RPG", description=self.view_ref.api.get_status_text(), color=0x5865f2)
        embed.set_image(url="attachment://maze.png")
        # 場所ごとにボタン切り替え
        self.view_ref.clear_items()
        self.view_ref.add_item(MazeButton('↑', 'up', self.view_ref))
        self.view_ref.add_item(MazeButton('↓', 'down', self.view_ref))
        self.view_ref.add_item(MazeButton('←', 'left', self.view_ref))
        self.view_ref.add_item(MazeButton('→', 'right', self.view_ref))
        # ショップ
        if self.view_ref.api.can_shop():
            self.view_ref.add_item(ShopButton(self.view_ref))
        # クエスト
        if self.view_ref.api.can_quest():
            self.view_ref.add_item(QuestButton(self.view_ref))
        # バトル
        if not self.view_ref.api.in_battle and cell == 'road' and random.random() < 0.15:
            self.view_ref.api.start_battle()
            self.view_ref.add_item(BattleButton(self.view_ref))
            if embed.description:
                embed.description += "\n敵が現れた! バトル開始!"
            else:
                embed.description = "敵が現れた! バトル開始!"
        if self.view_ref.api.in_battle:
            self.view_ref.clear_items()
            self.view_ref.add_item(BattleButton(self.view_ref))
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self.view_ref)

class MazeView(discord.ui.View):
    def __init__(self, api, user_id, timeout=180):
        super().__init__(timeout=timeout)
        self.api = api
        self.user_id = user_id
        self.done = asyncio.Event()
        self.add_item(MazeButton('↑', 'up', self))
        self.add_item(MazeButton('↓', 'down', self))
        self.add_item(MazeButton('←', 'left', self))
        self.add_item(MazeButton('→', 'right', self))
class ShopButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="ショップ", style=discord.ButtonStyle.success)
        self.view_ref = view
    async def callback(self, interaction: discord.Interaction):
        api = self.view_ref.api
        if not api.can_shop():
            await interaction.response.send_message("ここでは買い物できません。", ephemeral=True)
            return
        items = api.shop_items
        desc = "\n".join([f"{i+1}. {item['name']}({item['price']}en): {item['desc']}" for i, item in enumerate(items)])
        embed = discord.Embed(title="🛒 ショップ", description=desc+"\n購入したい番号を半角で送信してください。キャンセルは`cancel`。", color=0x2ecc71)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        def check(m):
            return m.author.id == interaction.user.id and m.channel == interaction.channel
        try:
            msg = await interaction.client.wait_for('message', timeout=30, check=check)
            if msg.content.lower() == 'cancel':
                await msg.reply("キャンセルしました。")
                return
            idx = int(msg.content)-1
            ok, res = api.buy_item(idx)
            await msg.reply(res)
        except Exception:
            await interaction.followup.send("タイムアウト/エラー", ephemeral=True)

class QuestButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="クエスト受注", style=discord.ButtonStyle.secondary)
        self.view_ref = view
    async def callback(self, interaction: discord.Interaction):
        ok, res = self.view_ref.api.accept_quest()
        await interaction.response.send_message(res, ephemeral=True)

class BattleButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="バトル", style=discord.ButtonStyle.danger)
        self.view_ref = view
    async def callback(self, interaction: discord.Interaction):
        api = self.view_ref.api
        if not api.in_battle:
            await interaction.response.send_message("バトル中ではありません。", ephemeral=True)
            return
        # バトル専用ビューを表示
        battle_view = BattleView(api, self.view_ref.user_id, self.view_ref)
        s = api.battle_state
        desc = f"勇者HP: {s.get('player_hp',0)} 敵HP: {s.get('enemy_hp',0)}"
        embed = discord.Embed(title="⚔️ バトル", description=desc, color=0xe74c3c)
        await interaction.response.edit_message(embed=embed, view=battle_view)

# バトル専用ビュー
class BattleView(discord.ui.View):
    def __init__(self, api, user_id, parent_view, timeout=60):
        super().__init__(timeout=timeout)
        self.api = api
        self.user_id = user_id
        self.parent_view = parent_view
        self.add_item(AttackButton(self))
        self.add_item(HealButton(self))
        # アイテムは全てボタン化（例：やくそう、つるぎ等）
        for item in set(api.inventory):
            if item == "やくそう":
                self.add_item(ItemButton(self, item))
    async def on_timeout(self):
        # バトル終了時は元のビューに戻す
        pass

class AttackButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="攻撃", style=discord.ButtonStyle.primary)
        self.view_ref = view
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.view_ref.user_id:
            await interaction.response.send_message("あなたの操作権限がありません。", ephemeral=True)
            return
        log, state = self.view_ref.api.battle_turn('attack')
        # プレイヤー攻撃後、敵が生きていれば敵ターンも自動で進める
        if self.view_ref.api.in_battle and state.get('turn') == 'enemy':
            enemy_log, state = self.view_ref.api.battle_turn('')
            log += enemy_log
        desc = "\n".join(log) + f"\n勇者HP: {state.get('player_hp',0)} 敵HP: {state.get('enemy_hp',0)}"
        embed = discord.Embed(title="⚔️ バトル", description=desc, color=0xe74c3c)
        # バトル終了ならMazeViewに戻す
        if not self.view_ref.api.in_battle:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            api = self.view_ref.api
            parent_view = self.view_ref.parent_view
            img = api.draw_map()
            file = discord.File(img, filename="maze.png")
            map_embed = discord.Embed(title="🗺️ 本格RPG", description=api.get_status_text(), color=0x5865f2)
            map_embed.set_image(url="attachment://maze.png")
            await interaction.edit_original_response(embed=map_embed, attachments=[file], view=parent_view)
        else:
            await interaction.response.edit_message(embed=embed, view=BattleView(self.view_ref.api, self.view_ref.user_id, self.view_ref.parent_view))

class HealButton(discord.ui.Button):
    def __init__(self, view):
        super().__init__(label="回復", style=discord.ButtonStyle.secondary)
        self.view_ref = view
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.view_ref.user_id:
            await interaction.response.send_message("あなたの操作権限がありません。", ephemeral=True)
            return
        log, state = self.view_ref.api.battle_turn('heal')
        if self.view_ref.api.in_battle and state.get('turn') == 'enemy':
            enemy_log, state = self.view_ref.api.battle_turn('')
            log += enemy_log
        desc = "\n".join(log) + f"\n勇者HP: {state.get('player_hp',0)} 敵HP: {state.get('enemy_hp',0)}"
        embed = discord.Embed(title="⚔️ バトル", description=desc, color=0xe74c3c)
        if not self.view_ref.api.in_battle:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            api = self.view_ref.api
            parent_view = self.view_ref.parent_view
            img = api.draw_map()
            file = discord.File(img, filename="maze.png")
            map_embed = discord.Embed(title="🗺️ 本格RPG", description=api.get_status_text(), color=0x5865f2)
            map_embed.set_image(url="attachment://maze.png")
            await interaction.edit_original_response(embed=map_embed, attachments=[file], view=parent_view)
        else:
            await interaction.response.edit_message(embed=embed, view=BattleView(self.view_ref.api, self.view_ref.user_id, self.view_ref.parent_view))

class ItemButton(discord.ui.Button):
    def __init__(self, view, item_name):
        super().__init__(label=f"アイテム({item_name})", style=discord.ButtonStyle.success)
        self.view_ref = view
        self.item_name = item_name
    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.view_ref.user_id:
            await interaction.response.send_message("あなたの操作権限がありません。", ephemeral=True)
            return
        # アイテム使用処理
        log = []
        used = False
        if self.item_name == "やくそう" and "やくそう" in self.view_ref.api.inventory:
            self.view_ref.api.inventory.remove("やくそう")
            self.view_ref.api.battle_state['player_hp'] += 10
            log.append("やくそうを使ってHPを10回復！")
            used = True
        else:
            log.append(f"{self.item_name}は使えません")
        s = self.view_ref.api.battle_state
        if self.view_ref.api.in_battle and s.get('turn') == 'enemy':
            enemy_log, s = self.view_ref.api.battle_turn('')
            log += enemy_log
        desc = "\n".join(log) + f"\n勇者HP: {s.get('player_hp',0)} 敵HP: {s.get('enemy_hp',0)}"
        embed = discord.Embed(title="⚔️ バトル", description=desc, color=0xe74c3c)
        if not self.view_ref.api.in_battle:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            api = self.view_ref.api
            parent_view = self.view_ref.parent_view
            img = api.draw_map()
            file = discord.File(img, filename="maze.png")
            map_embed = discord.Embed(title="🗺️ 本格RPG", description=api.get_status_text(), color=0x5865f2)
            map_embed.set_image(url="attachment://maze.png")
            await interaction.edit_original_response(embed=map_embed, attachments=[file], view=parent_view)
        else:
            await interaction.response.edit_message(embed=embed, view=BattleView(self.view_ref.api, self.view_ref.user_id, self.view_ref.parent_view))
# --- ゲーム登録 ---
def register_game(game_manager):
    game_manager.register_game(
        'rpg',
        '迷路RPG（ソロ専用/ボタン操作/画像UI）',
        matching=False,
        start_func=start_rpg,
        min_players=1,
        max_players=1
    )

async def start_rpg(ctx, players):
    uid, uname = players[0]
    api = RPGAPI()
    img = api.draw_map()
    file = discord.File(img, filename="maze.png")
    embed = discord.Embed(title="🗺️ 本格RPG", description=api.get_status_text(), color=0x5865f2)
    embed.set_image(url="attachment://maze.png")
    view = MazeView(api, str(uid))
    msg = await ctx.send(embed=embed, file=file, view=view)
    try:
        await asyncio.wait_for(view.done.wait(), timeout=300)
    except asyncio.TimeoutError:
        await ctx.send("⏰ タイムアウトしました。")
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            await msg.edit(view=view)
        except Exception:
            pass
    await asyncio.sleep(5)
    try:
        await msg.delete()
    except Exception:
        pass
