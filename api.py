"""
Discord Bot API エンドポイント
Flask APIのエンドポイントを管理するモジュール
"""

import os
from datetime import datetime
from flask import Flask, jsonify, request
import utils


def register_api_routes(app: Flask, bot_instance=None):
    from API.youtubeEmbed import YoutubeEmbed

    @app.route("/youtube/<video_id>", methods=["GET"])
    def api_youtube_embed(video_id):
        """YouTube動画の埋め込み用OGP HTMLまたはリダイレクトを返すAPI"""
        ua = request.headers.get('User-Agent', '')
        print(f"[api_youtube_embed][DEBUG] video_id={video_id} User-Agent={ua}")
        ua_lc = ua.lower()
        bot_keywords = ["discord", "twitterbot", "slackbot", "facebookexternalhit", "telegrambot", "embed", "bot", "crawler", "spider"]
        is_bot = any(kw in ua_lc for kw in bot_keywords)
        print(f"[api_youtube_embed][DEBUG] is_bot={is_bot}")
        if is_bot:
            html = YoutubeEmbed.get_ogp_html(video_id, user_agent=ua)
            print(f"[api_youtube_embed][DEBUG] OGP HTML returned for bot UA")
            return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
        # 通常アクセスはYouTubeへリダイレクト
        info = YoutubeEmbed.get_embed_info(video_id)
        print(f"[api_youtube_embed][DEBUG] info={info}")
        if info.get("success"):
            print(f"[api_youtube_embed][DEBUG] Redirecting to {info['url']}")
            return '', 302, {'Location': info["url"]}
        else:
            print(f"[api_youtube_embed][DEBUG] Invalid YouTube Video ID")
            return 'Invalid YouTube Video ID', 400
    """
    FlaskアプリケーションにAPIルートを登録する
    
    Args:
        app: Flaskアプリケーションインスタンス
        bot_instance: Discord Botインスタンス
    """
    
    def check_api_key():
        """APIキー認証をチェックするヘルパー関数"""
        access_key = os.environ.get('Key')
        req_key = request.headers.get('X-API-Key') or request.args.get('Key')
        
        if access_key and req_key != access_key:
            return False
        return True

    @app.route("/database", methods=["GET"])
    def api_database():
        """データベース全体を取得（管理用）"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        try:
            from DataBase import load_db_cache
            db = load_db_cache()
            return jsonify({'success': True, 'data': db, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route("/consolelog", methods=["GET"])
    def api_consolelog():
        """サーバーのコンソールログを取得（管理用）"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        try:
            # ログファイルのパス（例: ./server.log）
            log_path = os.environ.get('LOG_PATH', './server.log')
            if not os.path.exists(log_path):
                return jsonify({'success': False, 'error': f'ログファイルが存在しません: {log_path}'}), 404
            with open(log_path, encoding='utf-8') as f:
                log_content = f.read()[-10000:]  # 直近10000文字のみ返す
            return jsonify({'success': True, 'log': log_content, 'timestamp': datetime.now().isoformat()})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # 登録されたAPIエンドポイントをログ出力
    print("✔ API routes registered successfully")
    print("📋 Registered API endpoints:")
    api_routes = [
        ("/database", "GET", "データベース読み取り"),
        ("/youtube/<video_id>", "GET", "YouTube埋め込み情報取得"),
        ("/consolelog", "GET", "サーバーコンソールログ取得")
    ]
    for route, method, description in api_routes:
        print(f"  ✔ API登録: {route} (['{method}']) - {description}")
    print("🌐 API server ready")
