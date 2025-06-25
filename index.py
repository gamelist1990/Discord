import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import os
import json
import sys
import asyncio
import threading
import typing
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
from discord import app_commands
from typing import Any, Callable
import traceback

from DataBase import start_api_key_cleanup_loop
import utils

# APIサーバー統合用import
try:
    import server as api_manager_module
    API_MANAGER_AVAILABLE = True
except ImportError:
    API_MANAGER_AVAILABLE = False
    print("⚠️ server.py が見つかりません。API管理機能は無効です。")

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

# API管理機能
api_manager = None
api_manager_enabled = False

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

# グローバル変数の初期化
isBot = False
last_isBot_update = None
isBot_patch = None


# Flask ルート定義
@app.route("/")
def dashboard():
    return render_template("index.html")
def registerFlask(app, bot_instance):
    """
    Flask拡張APIの登録を一元化する関数。
    必要なAPI登録関数をここでまとめて呼び出す。
    """
    global api_manager, api_manager_enabled
    
    # API エンドポイントを登録
    try:
        import api
        # bot_start_timeをappに設定
        app.bot_start_time = bot_start_time
        api.register_api_routes(app, bot_instance)
        print("✔ APIエンドポイントを登録しました")
    except Exception as e:
        print(f"❌ APIエンドポイント登録エラー: {e}")
    
    # API管理機能を初期化
    if API_MANAGER_AVAILABLE:
        try:
            import server as api_manager_module
            api_manager = api_manager_module.integrate_with_flask_app(app)
            api_manager_enabled = True
            print("✔ API管理機能を有効化しました")
        except Exception as e:
            print(f"❌ API管理機能の初期化に失敗: {e}")
            api_manager_enabled = False


def run_flask():
    global bot_instance
    registerFlask(app, bot_instance)
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)


# 設定ファイルの読み書き
def load_config():
    return utils.load_config_file(CONFIG_FILE_NAME)


def save_config(config):
    return utils.save_config_file(CONFIG_FILE_NAME, config)


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
    # サブディレクトリも含めて全ての.pyをロード
    plugin_files = glob.glob(os.path.join(PLUGINS_DIR, "**", "*.py"), recursive=True)
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


def registerSlashCommand(bot, name, description, callback, parameters=None):
    """
    スラッシュコマンドを動的に登録する関数（使う側でasyncioやawait不要）。
    name: コマンド名
    description: コマンド説明
    callback: コマンド実行時のコールバック関数 (async def func(interaction, ...))
    parameters: パラメータのリスト [{"name": "user", "description": "ユーザー", "type": discord.Member, "required": False}, ...]
    """
    tree = bot.tree if hasattr(bot, 'tree') else None
    if not tree:
        print("❌ スラッシュコマンドツリーが見つかりません")
        return
    
    # 既存のコマンドがある場合は削除
    try:
        existing_command = tree.get_command(name)
        if existing_command:
            tree.remove_command(name)
    except:
        pass
    
    if parameters:
        # パラメータの数に応じて動的にコマンドを作成
        param_count = len(parameters)
        
        # describe辞書を作成
        describe_dict = {}
        for param in parameters:
            describe_dict[param["name"]] = param.get("description", "")
        
        if param_count == 1:
            # 1つのパラメータの場合
            param = parameters[0]
            param_name = param["name"]
            param_type = param.get("type", str)
            param_required = param.get("required", True)
            
            if param_type == discord.Member:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_member_required(interaction: discord.Interaction, user: discord.Member):
                        try:
                            await callback(interaction, user)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)
                    tree.add_command(cmd_member_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_member_optional(interaction: discord.Interaction, user: typing.Optional[discord.Member] = None):
                        try:
                            await callback(interaction, user)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)
                    tree.add_command(cmd_member_optional)
            elif param_type == str:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_str_required(interaction: discord.Interaction, text: str):
                        try:
                            await callback(interaction, text)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)
                    tree.add_command(cmd_str_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_str_optional(interaction: discord.Interaction, text: typing.Optional[str] = None):
                        try:
                            await callback(interaction, text)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)
                    tree.add_command(cmd_str_optional)
            elif param_type == int:
                if param_required:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_int_required(interaction: discord.Interaction, number: int):
                        try:
                            await callback(interaction, number)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)
                    tree.add_command(cmd_int_required)
                else:
                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_int_optional(interaction: discord.Interaction, number: typing.Optional[int] = None):
                        try:
                            await callback(interaction, number)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)
                    tree.add_command(cmd_int_optional)
            else:
                # その他の型（基本的なフォールバック）
                @app_commands.command(name=name, description=description)
                @app_commands.describe(**describe_dict)
                async def cmd_other(interaction: discord.Interaction, value: typing.Optional[str] = None):
                    try:
                        await callback(interaction, value)
                    except Exception as e:
                        print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                        await _handle_slash_error(interaction)
                tree.add_command(cmd_other)
        
        elif param_count == 2:
            # 2つのパラメータの場合
            param1 = parameters[0]
            param2 = parameters[1]
            
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_two_params(interaction: discord.Interaction, arg1: typing.Any, arg2: typing.Any):
                try:
                    await callback(interaction, arg1, arg2)
                except Exception as e:
                    print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                    await _handle_slash_error(interaction)
            tree.add_command(cmd_two_params)
        
        elif param_count == 3:
            # 3つのパラメータの場合
            param1 = parameters[0]
            param2 = parameters[1]
            param3 = parameters[2]
            
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_three_params(interaction: discord.Interaction, arg1: typing.Any, arg2: typing.Any, arg3: typing.Any):
                try:
                    await callback(interaction, arg1, arg2, arg3)
                except Exception as e:
                    print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                    await _handle_slash_error(interaction)
            tree.add_command(cmd_three_params)
        
        else:
            # 4つ以上のパラメータの場合（一般的なケース）
            @app_commands.command(name=name, description=description)
            @app_commands.describe(**describe_dict)
            async def cmd_multi_params(interaction: discord.Interaction):
                try:
                    # 複数パラメータは現在サポートしていないが、フォールバック
                    await callback(interaction)
                except Exception as e:
                    print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                    await _handle_slash_error(interaction)
            tree.add_command(cmd_multi_params)
    else:
        # パラメータなしの場合（従来通り）
        @app_commands.command(name=name, description=description)
        async def cmd_no_params(interaction: discord.Interaction):
            try:
                await callback(interaction)
            except Exception as e:
                print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                await _handle_slash_error(interaction)
        tree.add_command(cmd_no_params)
    
    print(f"✔ スラッシュコマンド /{name} を登録しました。")


async def _handle_slash_error(interaction: discord.Interaction):
    """スラッシュコマンドエラーの共通処理"""
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "❌ コマンドの実行中にエラーが発生しました。", 
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ コマンドの実行中にエラーが発生しました。", 
                ephemeral=True
            )
    except:
        pass


# --- Botイベントハンドラ管理 ---
_event_handlers = {}

def registerBotEvent(bot, event_name: str, handler):
    if bot is None:
        print(f"[registerBotEvent] bot is None, cannot register {event_name}")
        return
    if event_name not in _event_handlers:
        _event_handlers[event_name] = {}
        # 既存の@bot.event登録済み関数も最初に保存
        orig = getattr(bot, event_name, None)
        if orig and not any(orig is h for h in _event_handlers[event_name].values()):
            _event_handlers[event_name][id(orig)] = orig
    # 多重登録防止: 既に同じhandlerがあればスキップ
    if handler in _event_handlers[event_name].values():
        return
    handler_id = id(handler)
    _event_handlers[event_name][handler_id] = handler
    # プロキシを再生成
    async def _event_proxy(*args, **kwargs):
        for h in list(_event_handlers[event_name].values()):
            await h(*args, **kwargs)
    setattr(bot, event_name, _event_proxy)

def unregisterBotEvent(bot, event_name: str, handler):
    if bot is None:
        print(f"[unregisterBotEvent] bot is None, cannot unregister {event_name}")
        return
    if event_name in _event_handlers:
        handler_id = id(handler)
        if handler_id in _event_handlers[event_name]:
            del _event_handlers[event_name][handler_id]
    # プロキシを再生成
    async def _event_proxy(*args, **kwargs):
        for h in list(_event_handlers[event_name].values()):
            await h(*args, **kwargs)
    setattr(bot, event_name, _event_proxy)


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
    intents.presences = True
    intents.typing = True
    bot: commands.Bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
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

        # スラッシュコマンドの同期
        try:
            print("⏳ スラッシュコマンドを同期中...")
            synced = await bot.tree.sync()
            print(f"✔ {len(synced)} 個のスラッシュコマンドを同期しました。")
            if synced:
                print("📋 同期されたコマンド:")
                for cmd in synced:
                    print(f"  - /{cmd.name}: {cmd.description}")
        except Exception as e:
            print(f"❌ スラッシュコマンド同期エラー: {e}")

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
        traceback.print_exc()

    @bot.event
    async def on_command_error(ctx, error):
        print(f"❌ コマンドエラー: {error}")

    @bot.event
    async def on_application_command_error(interaction, error):
        print(f"❌ スラッシュコマンドエラー: {error}")

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
