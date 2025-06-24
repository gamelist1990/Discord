"""
API管理モジュール
FlaskアプリケーションのAPI登録/解除/管理を効率化
"""

import os
import socket
import requests
import platform
import psutil
from datetime import datetime
from flask import Flask, jsonify, request
from functools import wraps
import time
from collections import defaultdict
from typing import Optional, Dict, Any, List, Callable

# API管理クラス
class APIManager:
    def __init__(self, flask_app: Flask):
        self.app = flask_app
        self.registered_apis = {}
        self.api_stats = defaultdict(int)
        self.rate_limits = {}
        
    def register_api(self, route: str, methods: List[str], handler: Callable, 
                    name: Optional[str] = None, description: str = "", auth_required: bool = True,
                    rate_limit: Optional[Dict] = None):
        """APIエンドポイントを登録"""
        if name is None:
            name = handler.__name__
            
        # レート制限デコレータを適用
        if rate_limit:
            handler = self._apply_rate_limit(handler, rate_limit)
            
        # 認証デコレータを適用
        if auth_required:
            handler = self._apply_auth(handler)
            
        # 統計デコレータを適用
        handler = self._apply_stats(handler, name)
        
        # Flaskにルートを登録
        self.app.add_url_rule(route, name, handler, methods=methods)
        
        # 管理情報を保存
        self.registered_apis[name] = {
            'route': route,
            'methods': methods,
            'description': description,
            'auth_required': auth_required,
            'rate_limit': rate_limit,
            'registered_at': datetime.now().isoformat()
        }
        
        print(f"✔ API登録: {route} ({methods}) - {description}")
        
    def unregister_api(self, name: str):
        """APIエンドポイントを登録解除"""
        if name in self.registered_apis:
            # Flask URL mapから削除（実際は困難なので警告のみ）
            print(f"⚠️ API登録解除: {name} (Flaskの制限により完全な削除は困難)")
            del self.registered_apis[name]
            return True
        return False
        
    def get_api_list(self) -> Dict[str, Any]:
        """登録済みAPI一覧を取得"""
        return {
            'apis': self.registered_apis,
            'total_count': len(self.registered_apis),
            'stats': dict(self.api_stats)
        }
        
    def get_api_stats(self) -> Dict[str, Any]:
        """API使用統計を取得"""
        return {
            'call_counts': dict(self.api_stats),
            'rate_limits': dict(self.rate_limits),
            'total_calls': sum(self.api_stats.values())
        }
        
    def _apply_auth(self, handler: Callable) -> Callable:
        """認証デコレータを適用"""
        @wraps(handler)
        def decorated(*args, **kwargs):
            access_key = os.environ.get('Key')
            req_key = request.headers.get('X-API-Key') or request.args.get('Key')
            
            if access_key and req_key != access_key:
                return jsonify({'error': 'Forbidden'}), 403
                
            return handler(*args, **kwargs)
        return decorated
        
    def _apply_rate_limit(self, handler: Callable, config: Dict) -> Callable:
        """レート制限デコレータを適用"""
        max_requests = config.get('max_requests', 60)
        window = config.get('window', 60)
        
        @wraps(handler)
        def decorated(*args, **kwargs):
            client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', 
                                          request.environ.get('REMOTE_ADDR', '127.0.0.1'))
            now = time.time()
            key = f"{handler.__name__}:{client_ip}"
            
            if key not in self.rate_limits:
                self.rate_limits[key] = []
                
            # 古いリクエストを削除
            self.rate_limits[key] = [
                req_time for req_time in self.rate_limits[key] 
                if now - req_time < window
            ]
            
            # リクエスト数チェック
            if len(self.rate_limits[key]) >= max_requests:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'{max_requests} requests per {window} seconds allowed'
                }), 429
                
            # 現在のリクエストを記録
            self.rate_limits[key].append(now)
            
            return handler(*args, **kwargs)
        return decorated
        
    def _apply_stats(self, handler: Callable, name: str) -> Callable:
        """統計デコレータを適用"""
        @wraps(handler)
        def decorated(*args, **kwargs):
            self.api_stats[name] += 1
            return handler(*args, **kwargs)
        return decorated

# ユーティリティ関数群
def get_global_ip() -> Optional[str]:
    """グローバルIPアドレスを取得"""
    try:
        services = [
            'https://api.ipify.org',
            'https://checkip.amazonaws.com',
            'https://icanhazip.com'
        ]
        
        for service in services:
            try:
                response = requests.get(service, timeout=5)
                if response.status_code == 200:
                    return response.text.strip()
            except:
                continue
        return None
    except Exception:
        return None

def get_local_ip() -> str:
    """ローカルIPアドレスを取得"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def get_system_info() -> Dict[str, Any]:
    """システム情報を取得"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'platform': platform.platform(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': cpu_percent,
            'memory': {
                'total': memory.total,
                'available': memory.available,
                'percent': memory.percent,
                'used': memory.used
            },
            'disk': {
                'total': disk.total,
                'used': disk.used,
                'free': disk.free,
                'percent': (disk.used / disk.total) * 100
            }
        }
    except Exception as e:
        return {'error': f'Failed to get system info: {str(e)}'}

def get_listening_ports() -> List[Dict[str, Any]]:
    """リスニングポートを取得"""
    try:
        connections = psutil.net_connections(kind='inet')
        listening_ports = []
        
        for conn in connections:
            if conn.status == psutil.CONN_LISTEN and conn.laddr:
                listening_ports.append({
                    'port': conn.laddr.port,
                    'address': conn.laddr.ip,
                    'family': 'IPv4' if conn.family == socket.AF_INET else 'IPv6',
                    'type': 'TCP' if conn.type == socket.SOCK_STREAM else 'UDP'
                })
        
        return listening_ports
    except Exception:
        return []

def check_port_status(host: str, port: int, timeout: int = 3) -> bool:
    """ポートの接続可能性をチェック"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

# API管理用のFlaskエンドポイント生成関数
def setup_management_apis(api_manager: APIManager):
    """管理用APIエンドポイントをセットアップ"""
    
    def api_management_status():
        """API管理状況を返す"""
        return jsonify({
            'management': api_manager.get_api_list(),
            'stats': api_manager.get_api_stats(),
            'timestamp': datetime.now().isoformat()
        })
    
    def api_system_resources():
        """システムリソース情報を返す"""
        return jsonify({
            'system': get_system_info(),
            'network': {
                'global_ip': get_global_ip(),
                'local_ip': get_local_ip(),
                'listening_ports': get_listening_ports()
            },
            'timestamp': datetime.now().isoformat()
        })
    
    def api_port_check():
        """ポート接続チェック"""
        host = request.args.get('host', get_local_ip())
        port = request.args.get('port', type=int)
        
        if not port:
            return jsonify({'error': 'Port parameter is required'}), 400
        
        if not (1 <= port <= 65535):
            return jsonify({'error': 'Port must be between 1 and 65535'}), 400
        
        is_open = check_port_status(host, port)
        
        return jsonify({
            'host': host,
            'port': port,
            'is_open': is_open,
            'timestamp': datetime.now().isoformat()
        })
    
    def api_simple_address():
        """シンプルなアドレス情報"""
        return jsonify({
            'address': {
                'global_ip': get_global_ip(),
                'local_ip': get_local_ip(),
                'ports': {
                    'dashboard': 5000,
                    'management': 5001
                }
            },
            'timestamp': datetime.now().isoformat()
        })
    
    # 管理APIを登録
    api_manager.register_api(
        '/api/management/status', ['GET'], api_management_status,
        name='management_status', description='API管理状況', auth_required=True
    )
    
    api_manager.register_api(
        '/api/management/resources', ['GET'], api_system_resources,
        name='system_resources', description='システムリソース情報', auth_required=True,
        rate_limit={'max_requests': 30, 'window': 60}
    )
    
    api_manager.register_api(
        '/api/management/port-check', ['GET'], api_port_check,
        name='port_check', description='ポート接続チェック', auth_required=False,
        rate_limit={'max_requests': 20, 'window': 60}
    )
    
    api_manager.register_api(
        '/api/simple/address', ['GET'], api_simple_address,
        name='simple_address', description='シンプルアドレス情報', auth_required=False
    )

# メイン統合関数
def integrate_with_flask_app(flask_app: Flask) -> APIManager:
    """FlaskアプリケーションにAPI管理機能を統合"""
    api_manager = APIManager(flask_app)
    setup_management_apis(api_manager)
    
    print("✔ API管理機能を統合しました")
    return api_manager

# 後方互換性のための関数
def run_server():
    """後方互換性のための空関数"""
    print("⚠️ server.pyは管理モジュールに変更されました。index.pyから統合してください。")
