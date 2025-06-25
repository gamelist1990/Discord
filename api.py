"""
Discord Bot API エンドポイント
Flask APIのエンドポイントを管理するモジュール
"""

import os
import json
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
    
    def get_bot_info():
        """Bot情報を取得するヘルパー関数"""
        if bot_instance:
            return {
                'name': bot_instance.user.name if bot_instance.user else 'Bot',
                'is_ready': bot_instance.is_ready(),
                'server_count': len(bot_instance.guilds) if bot_instance.guilds else 0
            }
        return {
            'name': 'Bot',
            'is_ready': False,
            'server_count': 0
        }
    
    def check_api_key():
        """APIキー認証をチェックするヘルパー関数"""
        access_key = os.environ.get('Key')
        req_key = request.headers.get('X-API-Key') or request.args.get('Key')
        
        if access_key and req_key != access_key:
            return False
        return True
    
    @app.route("/api/network/info")
    def api_network_info():
        """ネットワーク情報API"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        
        global_ip = utils.get_global_ip()
        local_ip = utils.get_local_ip()
        network_interfaces = utils.get_network_info()
        
        return jsonify({
            'global_ip': global_ip,
            'local_ip': local_ip,
            'interfaces': network_interfaces,
            'ports': {
                'bot_dashboard': 5000,
                'api_manager': 5001  # api_manager_enabled は import で解決
            },
            'timestamp': datetime.now().isoformat()
        })

    @app.route("/api/system/info")
    def api_system_info():
        """システム情報API"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        
        system_info = utils.get_system_info()
        global_ip = utils.get_global_ip()
        local_ip = utils.get_local_ip()
        bot_info = get_bot_info()
        
        return jsonify({
            'system': system_info,
            'network': {
                'global_ip': global_ip,
                'local_ip': local_ip
            },
            'bot': {
                'name': bot_info['name'],
                'status': 'Online' if bot_info['is_ready'] else 'Offline',
                'server_count': bot_info['server_count'],
                'start_time': getattr(app, 'bot_start_time', datetime.now()).isoformat()
            },
            'timestamp': datetime.now().isoformat()
        })

    @app.route("/api/ip")
    def api_ip_info():
        """IP情報のみを返すシンプルなAPI"""
        # 認証なしでも利用可能（パブリックAPI）
        access_key = os.environ.get('Key')
        req_key = request.headers.get('X-API-Key') or request.args.get('Key')
        
        if access_key and req_key and req_key != access_key:
            return jsonify({'error': 'Forbidden'}), 403
        
        global_ip = utils.get_global_ip()
        local_ip = utils.get_local_ip()
        
        return jsonify({
            'global_ip': global_ip,
            'local_ip': local_ip,
            'timestamp': datetime.now().isoformat()
        })

    @app.route("/api/ports")
    def api_ports_info():
        """ポート情報API"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        
        try:
            listening_ports = utils.get_listening_ports()
            
            return jsonify({
                'listening_ports': listening_ports,
                'bot_ports': {
                    'dashboard': 5000,
                    'api_manager': 5001
                },
                'global_ip': utils.get_global_ip(),
                'local_ip': utils.get_local_ip(),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            return jsonify({'error': f'ポート情報取得エラー: {str(e)}'}), 500

    @app.route("/api/health")
    def api_health_check():
        """ヘルスチェックAPI"""
        bot_info = get_bot_info()
        start_time = getattr(app, 'bot_start_time', datetime.now())
        
        return jsonify({
            'status': 'healthy',
            'bot_online': bot_info['is_ready'],
            'api_manager_enabled': True,  # 設定に応じて変更可能
            'timestamp': datetime.now().isoformat(),
            'uptime': (datetime.now() - start_time).total_seconds()
        })

    @app.route("/api/full-status")
    def api_full_status():
        """完全なステータス情報API"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        
        global_ip = utils.get_global_ip()
        local_ip = utils.get_local_ip()
        system_info = utils.get_system_info()
        network_info = utils.get_network_info()
        bot_info = get_bot_info()
        start_time = getattr(app, 'bot_start_time', datetime.now())
        
        uptime = ""
        if hasattr(utils, 'format_uptime'):
            uptime = utils.format_uptime(start_time)
        
        return jsonify({
            'network': {
                'global_ip': global_ip,
                'local_ip': local_ip,
                'interfaces': network_info
            },
            'system': system_info,
            'bot': {
                'name': bot_info['name'],
                'status': 'Online' if bot_info['is_ready'] else 'Offline',
                'server_count': bot_info['server_count'],
                'uptime': uptime,
                'start_time': start_time.isoformat(),
                'is_ready': bot_info['is_ready']
            },
            'services': {
                'dashboard_port': 5000,
                'api_manager_port': 5001,
                'api_manager_enabled': True
            },
            'timestamp': datetime.now().isoformat()
        })

    @app.route("/api/server/address")
    def api_simple_address():
        """サーバーのIPとポート情報を返すシンプルなAPI"""
        global_ip = utils.get_global_ip()
        local_ip = utils.get_local_ip()
        
        return jsonify({
            'server': {
                'global_ip': global_ip,
                'local_ip': local_ip,
                'ports': {
                    'dashboard': 5000,
                    'api_manager': 5001
                }
            },
            'timestamp': datetime.now().isoformat()
        })

    

    @app.route("/database", methods=['GET'])
    def api_database():
        """database.jsonの内容を返すAPI (fetch_merge_db.py用)"""
        database_path = "database.json"
        
        # Keyパラメータの確認（オプション）
        provided_key = request.args.get('Key')
        
        # 環境変数またはconfig.jsonからAPIキーを取得
        expected_key = os.getenv('Key')
        if not expected_key:
            try:
                from index import load_config
                config = load_config()
                expected_key = config.get('Key')
            except:
                pass
        
        # キー認証（キーが設定されている場合のみ）
        if expected_key and provided_key != expected_key:
            return jsonify({
                'error': 'Invalid or missing API key',
                'message': 'Access denied'
            }), 401
        
        try:
            # database.jsonファイルの存在確認
            if not os.path.exists(database_path):
                return jsonify({
                    'error': 'Database file not found',
                    'message': f'{database_path} does not exist',
                    'timestamp': datetime.now().isoformat()
                }), 404
            
            # database.jsonの内容を読み込み
            with open(database_path, 'r', encoding='utf-8') as f:
                database_content = json.load(f)
            
            return jsonify({
                'success': True,
                'data': database_content,
                'file_path': database_path,
                'timestamp': datetime.now().isoformat()
            })
            
        except json.JSONDecodeError as e:
            return jsonify({
                'error': 'Invalid JSON format',
                'message': f'Failed to parse {database_path}: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }), 500
            
        except Exception as e:
            return jsonify({
                'error': 'Internal server error',
                'message': f'Failed to read database: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }), 500

    @app.route("/api/database/update", methods=['POST'])
    def api_database_update():
        """database.jsonを更新するAPI"""
        if not check_api_key():
            return jsonify({'error': 'Forbidden'}), 403
        
        database_path = "database.json"
        
        try:
            # リクエストからJSONデータを取得
            update_data = request.get_json()
            if not update_data:
                return jsonify({
                    'error': 'No JSON data provided',
                    'message': 'Request body must contain valid JSON'
                }), 400
            
            # 現在のdatabase.jsonを読み込み（存在する場合）
            current_data = {}
            if os.path.exists(database_path):
                with open(database_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
            
            # データを更新（マージ）
            if isinstance(update_data, dict) and isinstance(current_data, dict):
                current_data.update(update_data)
            else:
                current_data = update_data
            
            # バックアップ作成
            backup_path = f"{database_path}.bak"
            if os.path.exists(database_path):
                import shutil
                shutil.copy2(database_path, backup_path)
            
            # 更新されたデータを保存
            with open(database_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            
            return jsonify({
                'success': True,
                'message': 'Database updated successfully',
                'backup_created': backup_path,
                'timestamp': datetime.now().isoformat()
            })
            
        except json.JSONDecodeError as e:
            return jsonify({
                'error': 'Invalid JSON format',
                'message': f'Failed to parse JSON: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }), 400
            
        except Exception as e:
            return jsonify({
                'error': 'Internal server error',
                'message': f'Failed to update database: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }), 500

    # 登録されたAPIエンドポイントをログ出力
    print("✔ API routes registered successfully")
    print("📋 Registered API endpoints:")
    api_routes = [
        ("/api/network/info", "GET", "ネットワーク情報"),
        ("/api/system/info", "GET", "システム情報"),
        ("/api/ip", "GET", "IP情報"),
        ("/api/ports", "GET", "ポート情報"),
        ("/api/health", "GET", "ヘルスチェック"),
        ("/api/full-status", "GET", "完全なステータス情報"),
        ("/api/server/address", "GET", "サーバーアドレス情報"),
        ("/database", "GET", "データベース読み取り"),
        ("/api/database/update", "POST", "データベース更新")
    ]
    
    for route, method, description in api_routes:
        print(f"  ✔ API登録: {route} (['{method}']) - {description}")
    
    print("🌐 API server ready")
