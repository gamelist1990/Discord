import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Unityイベント連携
from Unity.Module.discord_event import relay_discord_event

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
import base64
import requests
from waitress import serve

from DataBase import start_api_key_cleanup_loop
import utils

# APIサーバー統合用import（不要なAPIマネージャ関連を削除）

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
RATE_LIMIT_COUNT = 3
RATE_LIMIT_WINDOW = 5  # 秒
RATE_LIMIT_DURATION = 30 * 60  # 秒
user_command_timestamps = defaultdict(lambda: deque(maxlen=RATE_LIMIT_COUNT))
rate_limited_users = {}

# Bot状態管理用グローバル変数
bot_instance = None
bot_start_time = None
server_count = 0
bot_status = "Starting..."


async def update_isBot_periodically():
    global isBot, last_isBot_update, bot_instance, isBot_patch
    while True:
        # Botがオンラインかどうかを判定
        current = bot_instance is not None and bot_instance.is_ready()
        bot_name = (
            bot_instance.user.name if bot_instance and bot_instance.user else "Bot"
        )
        now = datetime.now()
        # 10分ごとにパッチとして最新情報を保存
        isBot_patch = {
            "isBot": current,
            "bot_name": bot_name,
            "timestamp": now.isoformat(),
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
    # API エンドポイントを登録
    try:
        import api

        # bot_start_timeをappに設定
        app.bot_start_time = bot_start_time
        api.register_api_routes(app, bot_instance)
        print("✔ APIエンドポイントを登録しました")
    except Exception as e:
        print(f"❌ APIエンドポイント登録エラー: {e}")


def run_flask():
    global bot_instance
    registerFlask(app, bot_instance)
    serve(app, host="0.0.0.0", port=5000)


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
    result = is_global_admin(user_id, config) or is_guild_admin(
        user_id, guild_id, config
    )
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
    tree = bot.tree if hasattr(bot, "tree") else None
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
                    async def cmd_member_required(
                        interaction: discord.Interaction, user: discord.Member
                    ):
                        try:
                            await callback(interaction, user)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)

                    tree.add_command(cmd_member_required)
                else:

                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_member_optional(
                        interaction: discord.Interaction,
                        user: typing.Optional[discord.Member] = None,
                    ):
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
                    async def cmd_str_required(
                        interaction: discord.Interaction, text: str
                    ):
                        try:
                            await callback(interaction, text)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)

                    tree.add_command(cmd_str_required)
                else:

                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_str_optional(
                        interaction: discord.Interaction,
                        text: typing.Optional[str] = None,
                    ):
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
                    async def cmd_int_required(
                        interaction: discord.Interaction, number: int
                    ):
                        try:
                            await callback(interaction, number)
                        except Exception as e:
                            print(f"❌ スラッシュコマンド /{name} 実行エラー: {e}")
                            await _handle_slash_error(interaction)

                    tree.add_command(cmd_int_required)
                else:

                    @app_commands.command(name=name, description=description)
                    @app_commands.describe(**describe_dict)
                    async def cmd_int_optional(
                        interaction: discord.Interaction,
                        number: typing.Optional[int] = None,
                    ):
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
                async def cmd_other(
                    interaction: discord.Interaction, value: typing.Optional[str] = None
                ):
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
            async def cmd_two_params(
                interaction: discord.Interaction, arg1: typing.Any, arg2: typing.Any
            ):
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
            async def cmd_three_params(
                interaction: discord.Interaction,
                arg1: typing.Any,
                arg2: typing.Any,
                arg3: typing.Any,
            ):
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
                "❌ コマンドの実行中にエラーが発生しました。", ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ コマンドの実行中にエラーが発生しました。", ephemeral=True
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
    from plugins import handle_custom_command

    global bot_instance, bot_start_time, server_count, bot_status

    load_dotenv()
    config = load_config()
    ensure_eula_agreed(config)

    # --renderオプションまたはRENDER環境変数が指定されている場合--
    is_render = is_render_env() or ("--render" in sys.argv)
    if is_render:
        print("[INFO] Render/--render検出: 先にFlaskサーバーを起動します")
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        print(
            "[INFO] Flaskサーバー起動後、180秒待機してからGithubからdatabase.jsonを取得します"
        )
        import time

        time.sleep(180)
        # Githubからdatabase.jsonを取得
        import asyncio as _asyncio

        _asyncio.run(fetch_latest_auto_commit_and_load_json())
        print("[INFO] database.json取得後、Discord Botを起動します")
    else:
        print("[INFO] 通常起動: Discord Botを直接起動します")

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
    bot = commands.Bot(
        command_prefix=PREFIX,
        intents=intents,
        help_command=None,
        allowed_installs=discord.app_commands.AppInstallationType(
            guild=True, user=True
        ),
        allowed_contexts=app_commands.AppCommandContext(
            guild=True, dm_channel=True, private_channel=True
        ),
    )
    bot_instance = bot

    async def start_periodic_tasks():
        await asyncio.sleep(5)  # Bot起動直後の安定化待ち
        asyncio.create_task(update_isBot_periodically())

    @bot.event
    async def on_ready():
        global server_count, bot_status
        print(f"✔ {bot.user} としてログインしました！")
        utils.set_bot_start_time()
        server_count = len(bot.guilds)
        bot_status = "Online"
        start_api_key_cleanup_loop()
        if not config.get("globalAdmins"):
            app_info = await bot.application_info()
            owner_id = app_info.owner.id
            config["globalAdmins"] = [str(owner_id)]
            save_config(config)
            print(
                f"✔ Botオーナー {app_info.owner} ({owner_id}) をグローバル管理者に自動登録しました。"
            )
        await load_plugins(bot)
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
        # Unity afterEventにも発火
        relay_discord_event("ready")

    @bot.event
    async def on_message(message):
        await handle_custom_command(message)
        relay_discord_event("message", message)

    @bot.event
    async def on_member_join(member):
        relay_discord_event("member_join", member)

    @bot.event
    async def on_member_remove(member):
        relay_discord_event("member_remove", member)

    asyncio.run(bot.start(token))


def isCommand(cmd_name):
    global bot_instance
    # 先頭の#を除去
    if bot_instance and hasattr(bot_instance, "commands"):
        return any(c.name == cmd_name for c in bot_instance.commands)
    return False


# push_only.py自動実行フラグ
RUN_PUSH_ON_EXIT = False
if "--render" in sys.argv:
    RUN_PUSH_ON_EXIT = True
    print("[INFO] --render指定: 終了時にpush_only.pyを自動実行します")

# GitHub API push機能（旧push_only.pyの内容を統合）
push_executed = False


def run_push():
    """GitHub APIを使用してdatabase.jsonをプッシュする"""
    global push_executed
    if RUN_PUSH_ON_EXIT and not push_executed:
        push_executed = True
        try:
            print("[INFO] database.jsonをGitHubにプッシュ中...")

            # 環境変数とコンフィグ
            GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
            REPO = "gamelist1990/Discord"
            FILE_PATH = "database.json"
            BRANCH = "main"
            COMMIT_MESSAGE = f"auto: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WebAPIでdatabase.jsonを更新"

            if not GITHUB_TOKEN:
                print("[ERROR] GITHUB_TOKEN環境変数が必要です。")
                return

            # --- 直近1時間以内のauto:コミットがあればpushしない ---
            print(f"[INFO] 直近1時間以内のauto:コミットを確認中...")
            since_time = (datetime.utcnow() - timedelta(hours=1)).isoformat() + "Z"
            commits_url = f"https://api.github.com/repos/{REPO}/commits?path={FILE_PATH}&sha={BRANCH}&since={since_time}"
            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            }
            r_commits = requests.get(commits_url, headers=headers)
            if r_commits.status_code == 200:
                commits = r_commits.json()
                for commit in commits:
                    msg = commit.get("commit", {}).get("message", "")
                    if msg.startswith("auto:"):
                        print(
                            "[INFO] 直近1時間以内にauto:コミットが存在するためpushをスキップします。"
                        )
                        print("✔ ファイル内容は最新の状態です（autoコミット済み）")
                        return
            else:
                print(
                    f"[WARN] コミット履歴の取得に失敗: {r_commits.status_code} {r_commits.text[:200]}"
                )

            # ファイルの存在確認
            if not os.path.exists(FILE_PATH):
                print(f"[ERROR] ファイル '{FILE_PATH}' が見つかりません。")
                return

            print(f"[INFO] ファイル '{FILE_PATH}' をbase64エンコード中...")
            # ファイル内容をbase64エンコード
            with open(FILE_PATH, "rb") as f:
                content = base64.b64encode(f.read()).decode()
            print(f"[INFO] エンコード完了。データ長: {len(content)} 文字")

            headers = {
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            }

            print(f"[INFO] 現在のファイルSHAを取得中... (branch: {BRANCH})")
            # 現在のファイルSHAを取得
            r = requests.get(
                f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}?ref={BRANCH}",
                headers=headers,
            )
            print(f"[DEBUG] GET /contents レスポンス: {r.status_code} {r.text[:200]}")

            if r.status_code == 200:
                response_data = r.json()
                sha = response_data["sha"]
                current_content = response_data["content"]
                print(f"[INFO] 取得したSHA: {sha}")
                print(f"[INFO] 現在のGitHubファイル内容を取得完了")
            elif r.status_code == 404:
                print(f"[INFO] ファイルがGitHub上に存在しません。新規作成します。")
                sha = None
                current_content = None
            else:
                print(
                    f"[ERROR] GitHub APIからファイル情報の取得に失敗: {r.status_code} - {r.text}"
                )
                return

            # 内容の比較
            if current_content is not None:
                print(f"[INFO] ローカルファイルとGitHubファイルの内容を比較中...")
                # GitHubから取得した内容は改行文字が含まれている可能性があるため、それを除去して比較
                github_content_cleaned = current_content.replace("\n", "")
                if content == github_content_cleaned:
                    print(
                        f"[INFO] ファイル内容に変更がありません。更新をスキップします。"
                    )
                    print("✔ ファイル内容は最新の状態です")
                    return
                else:
                    print(
                        f"[INFO] ファイル内容に変更が検出されました。更新を続行します。"
                    )
            else:
                print(
                    f"[INFO] 新規ファイルのため、内容比較をスキップして作成を続行します。"
                )

            # ファイルを更新
            print(f"[INFO] ファイルを更新中... (commit message: '{COMMIT_MESSAGE}')")
            data = {"message": COMMIT_MESSAGE, "content": content, "branch": BRANCH}
            # 既存ファイルの場合のみSHAを追加
            if sha is not None:
                data["sha"] = sha
            r = requests.put(
                f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}",
                headers=headers,
                json=data,
            )
            print(f"[DEBUG] PUT /contents レスポンス: {r.status_code} {r.text[:200]}")
            if r.status_code in (200, 201):
                print("✔ WebAPIでdatabase.jsonを更新しました")
            else:
                print(f"❌ エラー: {r.text}")

        except Exception as e:
            print(f"[ERROR] database.jsonプッシュ失敗: {e}")


def is_render_env():
    return os.environ.get("RENDER", "").lower() in ("1", "true", "yes")


async def fetch_latest_auto_commit_and_load_json():
    GITHUB_REPO = os.environ.get("GITHUB_REPO", "<user>/<repo>")
    FILE_PATH = "database.json"
    BRANCH = os.environ.get("GITHUB_BRANCH", "main")
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    if not GITHUB_TOKEN or GITHUB_REPO.startswith("<"):
        print("[WARN] GITHUB_TOKENまたはGITHUB_REPOが未設定です。スキップします。")
        return
    commits_url = f"https://api.github.com/repos/{GITHUB_REPO}/commits?path={FILE_PATH}&sha={BRANCH}&per_page=10"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    resp = requests.get(commits_url, headers=headers)
    if resp.status_code != 200:
        print(f"[ERROR] GitHubコミット取得失敗: {resp.status_code} {resp.text[:200]}")
        return
    commits = resp.json()
    auto_commit = next(
        (
            c
            for c in commits
            if c.get("commit", {}).get("message", "").startswith("auto:")
        ),
        None,
    )
    if not auto_commit:
        print("[INFO] auto:コミットが見つかりませんでした。")
        return
    sha = auto_commit["sha"]
    file_url = (
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}?ref={sha}"
    )
    file_resp = requests.get(file_url, headers=headers)
    if file_resp.status_code != 200:
        print(
            f"[ERROR] database.json取得失敗: {file_resp.status_code} {file_resp.text[:200]}"
        )
        return
    file_data = file_resp.json()
    import base64

    content = base64.b64decode(file_data["content"]).decode("utf-8")
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    print("[INFO] 最新autoコミットのdatabase.jsonをロードしました。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("[FATAL ERROR] index.pyで未処理の例外が発生しました:")
        import traceback

        traceback.print_exc()
        if RUN_PUSH_ON_EXIT:
            try:
                run_push()
            except Exception as e2:
                print(f"[ERROR] finallyでのrun_push失敗: {e2}")
        sys.exit(1)
    finally:
        if RUN_PUSH_ON_EXIT:
            try:
                run_push()
            except Exception as e2:
                print(f"[ERROR] finallyでのrun_push失敗: {e2}")
        sys.exit(0)
