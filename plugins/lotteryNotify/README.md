# 抽選通知システム (LotteryNotify)

Discord Bot用の抽選・キャンペーン自動監視システムです。複数のECサイトやキャンペーンサイトを定期的にチェックし、新しい抽選やキャンペーンが見つかったときにDiscordチャンネルに通知します。

## 🚀 機能概要

- **自動監視**: 30分ごとに自動で抽選・キャンペーン情報をチェック
- **複数サイト対応**: dショッピング、Amazon、楽天市場など複数のサイトに対応
- **重複防止**: 既にチェック済みの商品は通知しない
- **統一データベース**: 全モジュールで共通のデータベースを使用
- **リアルタイム通知**: 新しい抽選が見つかったらすぐにDiscordに通知
- **手動チェック**: コマンドによる手動チェック機能

## 📁 ファイル構成

```
lotteryNotify/
├── __init__.py                  # パッケージ初期化
├── lottery_database.py          # 統一データベース管理
├── README.md                   # このファイル
└── notifyList/                 # 抽選監視モジュール集
    ├── __init__.py
    ├── dshopping_switch2.py     # dショッピング Nintendo Switch2 監視
    ├── amazon_switch_monitor.py # Amazon Nintendo Switch 監視
    ├── rakuten_lottery_monitor.py # 楽天キャンペーン監視
    ├── quick_test.py           # クイックテスト
    └── comprehensive_test.py   # 総合テスト
```

## 🛠️ セットアップ

### 1. 依存関係のインストール
```bash
pip install discord.py aiohttp beautifulsoup4 lxml
```

### 2. 通知チャンネルの設定
Discordで以下のコマンドを実行:
```
#lottery <channel_id>
```

### 3. 通知の開始
設定完了後、30分ごとに自動で抽選チェックが開始されます。

## 💬 Discord コマンド

### 基本コマンド

| コマンド | 説明 |
|---------|------|
| `#lottery <channel_id>` | 指定チャンネルで抽選通知を開始 |
| `#lottery off` | 現在のサーバーで抽選通知を停止 |
| `#lottery status` | 現在の通知設定とシステム状態を表示 |
| `#lottery check` | 手動で抽選チェックを実行（デバッグ用） |

### 使用例

```bash
# 通知チャンネルを設定（channel_idは実際のチャンネルIDに置き換え）
#lottery 123456789012345678

# 設定状況を確認
#lottery status

# 手動でチェックを実行
#lottery check

# 通知を停止
#lottery off
```

## 📊 監視対象サイト

### 現在対応しているサイト

1. **dショッピング** (`dshopping_switch2.py`)
   - Nintendo Switch2の在庫監視
   - 新商品検出時に通知

2. **Amazon** (`amazon_switch_monitor.py`)
   - Nintendo Switch関連商品の監視
   - 価格情報も含めて通知

3. **楽天市場** (`rakuten_lottery_monitor.py`)
   - キャンペーン・抽選情報の監視
   - 新しいプレゼント企画を検出

## 🧪 テスト機能

### クイックテスト
特定モジュールの動作確認:
```bash
cd plugins/lotteryNotify/notifyList
python quick_test.py
```

### 総合テスト
全モジュールの動作確認:
```bash
cd plugins/lotteryNotify/notifyList
python comprehensive_test.py
```

### 個別モジュールテスト
```bash
cd plugins/lotteryNotify/notifyList
python comprehensive_test.py dshopping_switch2
```
