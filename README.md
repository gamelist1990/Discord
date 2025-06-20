# DiscordBot

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![discord.py](https://img.shields.io/badge/discord.py-2.3.0+-7289da?logo=discord)
![Flask](https://img.shields.io/badge/flask-2.3.0+-yellow?logo=flask)

## 概要
本プロジェクトは、Python製の多機能Discord Botです。Bot本体に加え、Webダッシュボード（Flask）やプラグイン機構、アンチスパム・管理者機能・匿名チャット・DM管理など、サーバー運営を強力にサポートする機能を備えています。

---

## 📦 主な技術スタック
- Python 3.10+
- [discord.py](https://github.com/Rapptz/discord.py)
- Flask
- python-dotenv
- aiohttp, requests, Pillow

## 🤖 Bot機能
- プラグインによるコマンド拡張（`plugins/`）
- 管理者/スタッフ専用コマンド
- 匿名チャット・DM管理
- メッセージ一括削除
- スパム・荒らし自動検知（アンチスパム）
- レートリミット/タイムアウト
- Webダッシュボード（http://0.0.0.0:5000/）
- データベース連携（`database.json`）
- EULA同意・管理者自動登録

## ⚙️ Bot設定
- `config.json`による管理者設定
- サーバーごとの管理者権限付与
- スタッフロール・アラートチャンネル設定

---

## 🚀 インストール方法

### 前提条件
- Python 3.10以上
- Discord Bot用トークン

### インストール手順
1. リポジトリをクローン
   ```bash
   git clone xxxxxxxxxxxxxxxx
   cd Discord
   ```
2. 依存関係をインストール
   ```bash
   pip install -r requirements.txt
   ```
3. 環境変数を設定
   - `.env`ファイルを作成し、以下を記入:
     ```env
     DISCORD_BOT_TOKEN=あなたのBotトークン
     Key=任意のAPIキー
     ```
4. 設定ファイルを編集（必要に応じて）
   - `config.json` で管理者や権限を設定

---

## 📖 使用方法

### Botの起動
```bash
python index.py
```

### Webダッシュボード
- [http://0.0.0.0:5000/](http://0.0.0.0:5000/) でBotの状態確認やDB閲覧が可能

### コマンド例
- `#help` ... コマンド一覧を表示
- `#admin add server` ... サーバー管理者を自動登録
- `#clear` ... メッセージ一括削除
- `#tell` ... 匿名メッセージ送信
- `#staff` ... スタッフ用コマンドグループ

---

## 🛡️ アンチスパム・セキュリティ
- テキスト/画像/メンション/トークンスパム自動検知
- タイムアウト・自動削除・アラート通知
- サーバーごとに検知設定可能（`database.json`）

## 🛠️ プラグイン開発
- `plugins/`配下に.pyファイルを追加し、`setup(bot)`関数を実装
- コマンド/イベント/管理機能を柔軟に拡張可能

---

## 📂 ディレクトリ構成
```
Discord/
├── index.py           # メインBot本体
├── DataBase.py        # DB管理・API
├── plugins/           # プラグイン群
├── antiModule/        # アンチスパム/荒らし対策
├── Staff/             # スタッフ用コマンド
├── slash/             # スラッシュコマンド
├── templates/         # Webダッシュボード用HTML
├── config.json        # Bot設定
├── database.json      # データベース
├── requirements.txt   # 依存パッケージ
└── ...
```

---

## 📝 ライセンス
- 本BotはMITライセンス等、プロジェクトのライセンスに従います。
- 利用規約（EULA）への同意が必須です。

---

## 👤 コントリビューター
- Botオーナー・管理者は`config.json`参照
- プルリク・Issue歓迎

---

## ⚠️ 注意事項
- Discordの利用規約・開発者ポリシーを遵守してください
- 本Botの利用は自己責任でお願いします
- サーバー管理者以外の無断利用は禁止

---

## 🌐 その他
- ドキュメント/詳細は随時追加予定
- 機能追加・バグ報告はIssueまで
