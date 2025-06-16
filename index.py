import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import os
import json
import sys
import asyncio
import threading
from discord.ext import commands
import discord
import importlib.util
import glob
import signal
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request
from functools import wraps

from DataBase import start_api_key_cleanup_loop

CONFIG_FILE_NAME = "config.json"
EULA_TEXT = """
========================= 利用規約 (EULA) =========================
このツールは Discord Bot の管理を支援する目的で提供されます。
開発者は、このツールの使用によって生じた、あるいは使用に関連して生じた
いかなる種類の損害（データ損失、アカウント停止、その他の不利益を含むが
これらに限定されない）についても、一切の責任を負いません。
このツールの使用は、完全に自己の責任において行われるものとします。
Discord の利用規約および開発者ポリシーを遵守してください。
=================================================================
"""
PREFIX = "#"
PLUGINS_DIR = "plugins"
RATE_LIMIT_COUNT = 4
RATE_LIMIT_WINDOW = 3  # 秒
RATE_LIMIT_DURATION = 30 * 60  # 秒
user_command_timestamps = defaultdict(lambda: deque(maxlen=RATE_LIMIT_COUNT))
rate_limited_users = {}

# Bot状態管理用グローバル変数
bot_instance = None
bot_start_time = None
server_count = 0
bot_status = "Starting..."

# 10分ごとのBotオンライン記録用
isBot = False
last_isBot_update = None
isBot_patch = None  # 最新情報のパッチ用

async def update_isBot_periodically():
    global isBot, last_isBot_update, bot_instance, isBot_patch
    while True:
        # Botがオンラインかどうかを判定
        current = bot_instance is not None and bot_instance.is_ready()
        bot_name = bot_instance.user.name if bot_instance and bot_instance.user else "Bot"
        now = datetime.now()
        # 10分ごとにパッチとして最新情報を保存
        isBot_patch = {
            'isBot': current,
            'bot_name': bot_name,
            'timestamp': now.isoformat()
        }
        isBot = current
        last_isBot_update = now
        await asyncio.sleep(600)  # 10分(600秒)ごとに更新

# Flask アプリケーション
app = Flask(__name__)


# Flask ルート定義
@app.route("/")
def dashboard():
    return render_template("index.html")


# /api/bot-status レート制限用
status_rate_limit = {
    'last_access': None,
    'count': 0
}
STATUS_RATE_LIMIT_WINDOW = 3  # 秒
STATUS_RATE_LIMIT_COUNT = 5   # 3秒間に5回まで

def status_rate_limiter(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        now = datetime.now()
        last = status_rate_limit['last_access']
        if last and (now - last).total_seconds() < STATUS_RATE_LIMIT_WINDOW:
            status_rate_limit['count'] += 1
        else:
            status_rate_limit['count'] = 1
        status_rate_limit['last_access'] = now
        if status_rate_limit['count'] > STATUS_RATE_LIMIT_COUNT:
            return jsonify({'error': 'Too many requests'}), 429
        return f(*args, **kwargs)
    return decorated_function

@app.route("/api/bot-status")
def api_bot_status():
    global bot_instance, bot_start_time, server_count, bot_status, isBot_patch
    uptime = ""
    if bot_start_time:
        uptime_delta = datetime.now() - bot_start_time
        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{days}日 {hours:02d}:{minutes:02d}:{seconds:02d}"

    patch = isBot_patch if isBot_patch else {'isBot': False, 'bot_name': 'Bot', 'timestamp': None}
    return jsonify({
        "bot_name": patch['bot_name'],
        "status": bot_status,
        "server_count": server_count,
        "uptime": uptime,
        "start_time": bot_start_time.isoformat() if bot_start_time else None,
        "isBot": patch['isBot'],
        "last_isBot_update": patch['timestamp']
    })

@app.route('/database')
def get_database():
    access_key = os.environ.get('Key')
    req_key = request.args.get('Key')
    if access_key and req_key != access_key:
        return jsonify({'error': 'Forbidden'}), 403
    try:
        with open('database.json', 'r', encoding='utf-8') as f:
            data = f.read()
        return app.response_class(data, mimetype='application/json')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def registerFlask(app, bot_instance):
    """
    Flask拡張APIの登録を一元化する関数。
    必要なAPI登録関数をここでまとめて呼び出す。
    """
    # 他のAPI


def run_flask():
    global bot_instance
    registerFlask(app, bot_instance)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


# 設定ファイルの読み書き
def load_config():
    if not os.path.exists(CONFIG_FILE_NAME):
        return {}
    with open(CONFIG_FILE_NAME, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE_NAME, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# EULA同意確認
def ensure_eula_agreed(config):
    if config.get("eulaAgreed"):
        print("ℹ️ 利用規約には既に同意済みです。")
        return True
    print(EULA_TEXT)
    agreed = (
        input("上記の利用規約に同意し、自己責任で使用しますか？ (y/N): ")
        .strip()
        .lower()
        == "y"
    )
    if agreed:
        config["eulaAgreed"] = True
        save_config(config)
        print("✔ 利用規約に同意しました。")
        return True
    else:
        print("ℹ️ 利用規約に同意されなかったため、ツールを終了します。")
        sys.exit(0)


# 管理者判定
def is_global_admin(user_id, config):
    return str(user_id) in config.get("globalAdmins", [])


def is_guild_admin(user_id, guild_id, config):
    return str(user_id) in config.get("guildAdmins", {}).get(str(guild_id), [])


def is_admin(user_id, guild_id, config): 
    result = is_global_admin(user_id, config) or is_guild_admin(user_id, guild_id, config)
    print(f"[DEBUG] is_admin: user_id={user_id}, guild_id={guild_id}, result={result}")
    return result


# プラグイン/コマンドの動的ロード
async def load_plugins(bot):
    if not os.path.exists(PLUGINS_DIR):
        os.makedirs(PLUGINS_DIR)
        print(f"⚠️ プラグインディレクトリ {PLUGINS_DIR} を作成しました。")
        return
    plugin_files = glob.glob(os.path.join(PLUGINS_DIR, "*.py"))
    if not plugin_files:
        print(f"ℹ️ 利用可能なプラグインが見つかりませんでした。")
        return
    for file in plugin_files:
        try:
            spec = importlib.util.spec_from_file_location(
                os.path.splitext(os.path.basename(file))[0], file
            )
            if spec is None or spec.loader is None:
                print(
                    f"❌ プラグイン {file} のロードエラー: specまたはloaderがNoneです"
                )
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "setup"):
                result = module.setup(bot)
                if asyncio.iscoroutine(result):
                    await result
                print(f"✔ プラグイン {file} をロードしました。")
        except Exception as e:
            print(f"❌ プラグイン {file} のロードエラー: {e}")


# Bot起動
def main():
    global bot_instance, bot_start_time, server_count, bot_status

    load_dotenv()
    config = load_config()
    ensure_eula_agreed(config)
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("❌ 環境変数 DISCORD_BOT_TOKEN が設定されていません。")
        sys.exit(1)

    bot_start_time = datetime.now()
    bot_status = "Starting..."

    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    intents.voice_states = True
    bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
    bot_instance = bot    
    
    async def start_periodic_tasks():
        await asyncio.sleep(5)  # Bot起動直後の安定化待ち
        asyncio.create_task(update_isBot_periodically())

    @bot.event
    async def on_ready():
        global server_count, bot_status
        print(f"✔ {bot.user} としてログインしました！")

        # サーバー数更新
        server_count = len(bot.guilds)
        bot_status = "Online"

        start_api_key_cleanup_loop()

        # グローバル管理者が未設定ならBotオーナーを自動登録
        if not config.get("globalAdmins"):
            app_info = await bot.application_info()
            owner_id = app_info.owner.id
            config["globalAdmins"] = [str(owner_id)]
            save_config(config)
            print(
                f"✔ Botオーナー {app_info.owner} ({owner_id}) をグローバル管理者に自動登録しました。"
            )
        
        # プラグインのロード
        await load_plugins(bot)
        
        # Botステータス
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"サーバー監視中 | {PREFIX}help",
            ),
            status=discord.Status.online,
        )
        print("ℹ️ Botステータス設定完了。")
        print(f"ℹ️ Webダッシュボード: http://0.0.0.0:5000/")

        await start_periodic_tasks()

    @bot.event
    async def on_guild_join(guild):
        global server_count
        server_count = len(bot.guilds)
        print(f"ℹ️ サーバー参加: {guild.name} (ID: {guild.id})")

    @bot.event
    async def on_guild_remove(guild):
        global server_count
        server_count = len(bot.guilds)
        print(f"ℹ️ サーバー離脱: {guild.name} (ID: {guild.id})")

    @bot.event
    async def on_message(message):
        if (
            message.author.bot
            or not message.guild
            or not message.content.startswith(PREFIX)
        ):
            return
        user_id = str(message.author.id)
        now = datetime.now()
        # コマンド名取得
        cmd_name = message.content[1:].split()[0] if message.content.startswith(PREFIX) else ""
        from index import isCommand
        is_cmd = isCommand(cmd_name)
        # コマンド使用時のレート制限（厳しめ）
        if is_cmd:
            expiry = rate_limited_users.get(user_id)
            if expiry and now < expiry:
                # 1分間timeout
                try:
                    until = discord.utils.utcnow() + timedelta(seconds=60)
                    await message.author.timeout(until, reason="コマンド連投による自動タイムアウト(1分)")
                except Exception:
                    pass
                return
            elif expiry:
                del rate_limited_users[user_id]
                user_command_timestamps[user_id].clear()
            timestamps = user_command_timestamps[user_id]
            timestamps.append(now)
            recent = [t for t in timestamps if (now - t).total_seconds() < RATE_LIMIT_WINDOW]
            if len(recent) >= RATE_LIMIT_COUNT:
                rate_limited_users[user_id] = now + timedelta(seconds=60)  # 1分
                user_command_timestamps[user_id].clear()
                try:
                    await message.author.send(
                        "⚠️ コマンドを短時間に送信しすぎたため、1分間タイムアウトされました。"
                    )
                except:
                    pass
                # 1分間timeout
                try:
                    until = discord.utils.utcnow() + timedelta(seconds=60)
                    await message.author.timeout(until, reason="コマンド連投による自動タイムアウト(1分)")
                except Exception:
                    pass
                return
        else:
            # 通常のレートリミット
            expiry = rate_limited_users.get(user_id)
            if expiry and now < expiry:
                return
            elif expiry:
                del rate_limited_users[user_id]
                user_command_timestamps[user_id].clear()
            timestamps = user_command_timestamps[user_id]
            timestamps.append(now)
            recent = [t for t in timestamps if (now - t).total_seconds() < RATE_LIMIT_WINDOW]
            if len(recent) >= RATE_LIMIT_COUNT:
                rate_limited_users[user_id] = now + timedelta(seconds=RATE_LIMIT_DURATION)
                user_command_timestamps[user_id].clear()
                try:
                    await message.author.send(
                        "⚠️ コマンドを短時間に送信しすぎたため、一時的に制限されました。約30分後に解除されます。"
                    )
                except:
                    pass
                return
        await bot.process_commands(message)

    @bot.event
    async def on_member_join(member):
        print(f"ℹ️ メンバー参加: {member}")

    @bot.event
    async def on_voice_state_update(member, before, after):
        print(f"ℹ️ ボイス状態更新: {member}")

    @bot.event
    async def on_error(event, *args, **kwargs):
        print(f"❌ イベントエラー: {event}")

    @bot.event
    async def on_command_error(ctx, error):
        print(f"❌ コマンドエラー: {error}")

    # Flask アプリケーションを別スレッドで起動
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    def handle_exit(signum, frame):
        print(f"\nℹ️ シグナル({signum})受信。終了処理を開始します...")
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(bot.close())
        except Exception as e:
            print(f"❌ 終了処理エラー: {e}")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    bot.run(token)


def isCommand(cmd_name):
    global bot_instance
    # 先頭の#を除去
    if bot_instance and hasattr(bot_instance, 'commands'):
        return any(c.name == cmd_name for c in bot_instance.commands)
    return False


if __name__ == "__main__":
    main()
