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

    @app.route("/api/full-status", methods=["GET"])
    def api_full_status():
        """Botとシステムのフルステータス"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        try:
            system_info = utils.get_system_info() if hasattr(utils, 'get_system_info') else {}
            return jsonify({
                'success': True,
                'bot': True,
                'system': system_info,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # 登録されたAPIエンドポイントをログ出力
    print("✔ API routes registered successfully")
    print("📋 Registered API endpoints:")
    api_routes = [
        ("/api/full-status", "GET", "完全なステータス情報"),
        ("/database", "GET", "データベース読み取り"),
        ("/youtube/<video_id>", "GET", "YouTube埋め込み情報取得")
    ]
    
    for route, method, description in api_routes:
        print(f"  ✔ API登録: {route} (['{method}']) - {description}")
    
    print("🌐 API server ready")
