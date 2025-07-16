"""
Discord Bot API エンドポイント
Flask APIのエンドポイントを管理するモジュール
"""

import os
from datetime import datetime
from flask import Flask, jsonify, request
import utils


def register_api_routes(app: Flask, bot_instance=None):
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
        ("/database", "GET", "データベース読み取り")
    ]
    
    for route, method, description in api_routes:
        print(f"  ✔ API登録: {route} (['{method}']) - {description}")
    
    print("🌐 API server ready")
