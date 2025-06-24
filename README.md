# Discord

![GitHub stars](https://img.shields.io/github/stars/gamelist1990/Discord)
![GitHub forks](https://img.shields.io/github/forks/gamelist1990/Discord)
![GitHub issues](https://img.shields.io/github/issues/gamelist1990/Discord)
![GitHub last commit](https://img.shields.io/github/last-commit/gamelist1990/Discord)
![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python)
![discord.py](https://img.shields.io/badge/discord.py-2.3.0-blue?logo=discord)
![License](https://img.shields.io/badge/license-Unspecified-lightgrey.svg)

高機能なDiscord Botプロジェクトです。  
サーバー管理、権限管理、スラッシュコマンド連携、Webダッシュボードなどの機能を提供します。

---

## 目次
- [概要](#概要)
- [主な機能](#主な機能)
- [インストール方法](#インストール方法)
- [使用方法](#使用方法)
- [設定ファイル](#設定ファイル)
- [環境変数](#環境変数)
- [管理者権限](#管理者権限)
- [APIエンドポイント](#apiエンドポイント)
- [ディレクトリ構成](#ディレクトリ構成)
- [ライセンス](#ライセンス)

---

## 概要

本リポジトリはPython製のDiscord Botです。  
Bot本体は`discord.py` v2.3系を基盤に、管理者権限判定、スラッシュコマンド、Webダッシュボード（Flask）等を実装しています。

---

## 主な機能

- **スラッシュコマンド対応**: `/コマンド`形式のBot操作
- **サーバー・メンバー管理**: 管理者・ギルド単位での権限管理
- **レートリミットと自動タイムアウト**: コマンド乱用ユーザーの自動制限
- **Webダッシュボード**: FlaskベースのWeb管理画面（`http://0.0.0.0:5000/`で起動）
- **データベース連携**: `database.json`ファイルによる管理
- **プラグインシステム**: `plugins/`ディレクトリによる機能拡張
- **動画通知システム**: YouTube等の動画新着通知・ライブ配信検知（XML/RSS活用、API不要、ベータ版）
- **EULA同意チェック**: 利用時のエンドユーザーライセンス同意必須
- **環境変数管理**: `python-dotenv`による安全なトークン等の管理
- **API連携**: `/api/bot-status`エンドポイントでBot状態取得

---

## 🚀 インストール方法

### 前提条件
- Python 3.9以上
- pip

### インストール手順

1. リポジトリをクローン
   ```bash
   git clone https://github.com/gamelist1990/Discord.git
   cd Discord
   ```

2. 依存関係をインストール
   ```bash
   pip install -r requirements.txt
   ```

3. 環境変数を設定
   - `.env`ファイルを作成し、最低限 `DISCORD_BOT_TOKEN` を設定
   ```bash
   # 例
   echo "DISCORD_BOT_TOKEN=あなたのBotトークン" > .env
   ```

4. 必要に応じて `config.json` の管理者リスト等を編集

---

## 📖 使用方法

### 開発/本番起動

```bash
python index.py
```

初回実行時、EULA（利用規約）への同意が必要です。

### コマンド例
- サーバーで `#help` でコマンド案内
- スラッシュコマンド： `/` から始まるコマンド
- 動画通知設定： `#info` で動画通知システムを開く（動画・ライブ配信の個別間隔監視）

### Webダッシュボード
- [http://0.0.0.0:5000/](http://0.0.0.0:5000/) で起動（Flask）

---

## 設定ファイル

### config.json

- `eulaAgreed`：EULA同意フラグ
- `globalAdmins`：グローバル管理者IDリスト
- `guildAdmins`：ギルドごとの管理者IDリスト

### database.json
- Botが扱うデータベース（JSON形式）

---

## 環境変数

- `DISCORD_BOT_TOKEN`：Botのトークン（必須）
- `Key`：WebAPI認証用キー（任意）

---

## 管理者権限

- `config.json`で管理者（グローバル・ギルド毎）を設定可能
- コマンド実行や特定の管理操作は管理者IDのみ許可

---

## 🎬 動画通知システム

新機能として、YouTube等の動画プラットフォームの新着動画を自動で通知するシステムを実装しました。

### 特徴
- **API不要**: XMLフィード（RSS）を活用してAPIキー無しで動作
- **個別チェック間隔**: 各チャンネルごとに3-60分の間隔を設定可能
- **ライブ配信検知**: 配信開始も自動検知・通知（ベータ版機能）
- **Modal UI**: Discord のModalとEmbedを活用した直感的な設定画面
- **複数チャンネル対応**: 複数のYouTubeチャンネルを同時監視可能
- **DataBase統合**: DataBase.pyによる設定管理
- **通常コマンド**: `#info` コマンドで簡単アクセス

### 使用方法
1. `#info` コマンドを実行
2. 「📹 動画通知を設定」ボタンをクリック
3. Modalで以下を入力：
   - YouTubeチャンネルURL
   - 通知先DiscordチャンネルID
   - チェック間隔（3-60分（1時間）、デフォルト30分）

### 監視仕様
- **個別チェック間隔**で自動チェック実行（各チャンネルごとに設定）
- チェック間隔内に投稿・配信開始されたコンテンツを通知
- 🎬 通常動画：新着動画通知
- 🔴 ライブ配信：配信開始通知（ベータ版）
- **チェック間隔制限**：最小3分、最大60分（1時間）
- **レート制限対策**：重複排除・キャッシュ・リクエスト間隔制御
- **カスタム通知メッセージ**：動画・ライブ別にメッセージをカスタマイズ可能
- DataBase.pyによる設定・状態管理
- 効率的な通知システム

### カスタムメッセージ機能
- 📝 **動画通知**と**ライブ配信通知**でそれぞれメッセージをカスタマイズ
- 🎨 **プレースホルダー対応**：
  - `{title}` - 動画/配信タイトル
  - `{url}` - 動画/配信URL
  - `{author}` - チャンネル名
  - `{published}` - 公開日時（動画のみ）
- 🔄 **デフォルトに戻す**機能付き
- 💬 **チャンネル別個別設定**で細かくカスタマイズ

### 対応URL形式
- `youtube.com/channel/UC...`
- `youtube.com/c/チャンネル名`
- `youtube.com/user/ユーザー名`
- `youtube.com/@ハンドル名`

---

## APIエンドポイント

- `/api/bot-status`  
  Botの状態情報を返却（Flaskアプリ）

- `/database?Key=xxx`  
  データベースJSON取得（Keyが一致する場合のみ）

---

## ディレクトリ構成

```
Discord/
├── index.py              # メインBotスクリプト
├── requirements.txt      # 依存パッケージ
├── config.json           # 設定ファイル
├── database.json         # データベース
├── video_notifications.json  # 動画通知設定（自動生成）
├── plugins/              # プラグイン拡張用
│   ├── info.py          # 動画通知システム（NEW）
│   └── ...              # その他のプラグイン
├── templates/            # Flask用テンプレート
├── .env                  # 環境変数ファイル（git管理外）
├── venv/                 # 仮想環境
└── ...
```

※ plugins/、templates/ディレクトリには追加の機能やWeb画面素材を配置

---

## ライセンス

本プロジェクトは現時点で明示的なライセンスが指定されていません。  
利用規約（EULA）に同意の上でご利用ください。

---

## 🔍 解析サマリー

- ソース: [GitHubリポジトリ](https://github.com/gamelist1990/Discord)
- プロジェクトタイプ: Discord Bot (Python)
- メイン言語: Python
- 依存関係: discord.py >=2.3.0, python-dotenv, flask, aiohttp, requests, Pillow
- 機能: スラッシュコマンド, 管理者判定, Web管理画面, プラグイン, 動画・ライブ通知システム（ベータ版）, EULA同意, レートリミット
- 設定ファイル: ✅ requirements.txt, ✅ config.json
- GitHub統計: ⭐ 0 stars, 🍴 0 forks
- ライセンス: 未指定（EULA同意必須）

---

> **ファイル一覧やディレクトリ情報は[GitHubのリポジトリページ](https://github.com/gamelist1990/Discord/tree/main)でご確認ください。  
> 本READMEは自動生成されました。情報の正確性については[要確認]部分も含みます。