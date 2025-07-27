
"""
ユーティリティ関数モジュール
Discord Botプロジェクトで使用される共通のユーティリティ関数をまとめたモジュール
"""

import os
import json
import platform
import random
import psutil
import socket
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import subprocess
import re

# グローバルIP取得のキャッシュ
_global_ip_cache = {
    'ip': None,
    'last_update': None,
    'cache_duration': 300  # 5分間キャッシュ
}

def get_global_ip() -> Optional[str]:
    """グローバルIPアドレスを取得（キャッシュ機能付き）"""
    global _global_ip_cache
    now = datetime.now()
    
    # キャッシュが有効な場合は返す
    if (_global_ip_cache['ip'] and 
        _global_ip_cache['last_update'] and 
        (now - _global_ip_cache['last_update']).total_seconds() < _global_ip_cache['cache_duration']):
        return _global_ip_cache['ip']
    
    try:
        # 複数のサービスを試行
        services = [
            'https://api.ipify.org',
            'https://httpbin.org/ip',
            'https://checkip.amazonaws.com',
            'https://icanhazip.com'
        ]
        
        for service in services:
            try:
                response = requests.get(service, timeout=3)
                if response.status_code == 200:
                    if 'ipify' in service or 'icanhazip' in service or 'amazonaws' in service:
                        ip = response.text.strip()
                    else:  # httpbin
                        ip = response.json().get('origin', '').split(',')[0].strip()
                    
                    # IPアドレスの簡単な検証
                    if ip and '.' in ip:
                        _global_ip_cache['ip'] = ip
                        _global_ip_cache['last_update'] = now
                        return ip
            except:
                continue
        return None
    except Exception as e:
        print(f"❌ グローバルIP取得エラー: {e}")
        return None

def get_local_ip() -> str:
    """ローカルIPアドレスを取得"""
    try:
        # Google DNSに接続して自分のローカルIPを取得
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except:
        return "127.0.0.1"

def get_system_info() -> Dict[str, Any]:
    """システム情報を取得"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'architecture': platform.architecture()[0],
            'processor': platform.processor(),
            'python_version': platform.python_version(),
            'cpu_count': psutil.cpu_count(),
            'cpu_percent': cpu_percent,
            'memory': {
                'total': memory.total,
                'available': memory.available,
                'percent': memory.percent,
                'used': memory.used,
                'free': memory.free
            },
            'disk': {
                'total': disk.total,
                'used': disk.used,
                'free': disk.free,
                'percent': (disk.used / disk.total) * 100
            },
            'boot_time': datetime.fromtimestamp(psutil.boot_time()).isoformat()
        }
    except Exception as e:
        return {'error': f'システム情報取得エラー: {str(e)}'}

def get_network_info() -> Dict[str, Any]:
    """ネットワーク情報を取得"""
    try:
        interfaces = {}
        for interface, addrs in psutil.net_if_addrs().items():
            interface_info = []
            for addr in addrs:
                if addr.family == socket.AF_INET:  # IPv4
                    interface_info.append({
                        'ip': addr.address,
                        'netmask': addr.netmask,
                        'broadcast': addr.broadcast,
                        'family': 'IPv4'
                    })
                elif addr.family == socket.AF_INET6:  # IPv6
                    interface_info.append({
                        'ip': addr.address,
                        'netmask': addr.netmask,
                        'family': 'IPv6'
                    })
            if interface_info:
                interfaces[interface] = interface_info
        
        return interfaces
    except Exception as e:
        return {'error': f'ネットワーク情報取得エラー: {str(e)}'}

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
    except Exception as e:
        print(f"❌ ポート情報取得エラー: {e}")
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

def validate_ip_address(ip: str) -> bool:
    """IPアドレスの形式を検証"""
    ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    return bool(re.match(ip_pattern, ip))

def ping_host(target: str, count: int = 4, timeout: int = 10) -> Dict[str, Any]:
    """指定したホストにpingを送信"""
    if not validate_ip_address(target):
        return {
            'target': target,
            'success': False,
            'error': 'Invalid IP address format',
            'timestamp': datetime.now().isoformat()
        }
    
    try:
        # プラットフォーム別pingコマンド
        if platform.system().lower() == 'windows':
            cmd = ['ping', '-n', str(count), target]
        else:
            cmd = ['ping', '-c', str(count), target]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        return {
            'target': target,
            'success': result.returncode == 0,
            'output': result.stdout,
            'error': result.stderr if result.returncode != 0 else None,
            'timestamp': datetime.now().isoformat()
        }
    except subprocess.TimeoutExpired:
        return {
            'target': target,
            'success': False,
            'error': 'Ping timeout',
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'target': target,
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

def get_geolocation_info(ip: Optional[str] = None) -> Dict[str, Any]:
    """IP地理情報を取得"""
    if ip is None:
        ip = get_global_ip()
    
    if not ip:
        return {
            'error': 'No IP address provided or detected',
            'timestamp': datetime.now().isoformat()
        }
    
    try:
        # 無料の地理情報API使用
        response = requests.get(f'http://ip-api.com/json/{ip}', timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'ip': ip,
                'location': data,
                'timestamp': datetime.now().isoformat()
            }
        else:
            return {
                'ip': ip,
                'error': 'Failed to get geolocation',
                'timestamp': datetime.now().isoformat()
            }
    except Exception as e:
        return {
            'ip': ip,
            'error': f'Geolocation service error: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }

def format_uptime(start_time: datetime) -> str:
    """稼働時間をフォーマット"""
    if not start_time:
        return "Unknown"
    
    uptime_delta = datetime.now() - start_time
    days = uptime_delta.days
    hours, remainder = divmod(uptime_delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    return f"{days}日 {hours:02d}:{minutes:02d}:{seconds:02d}"

def format_bytes(bytes_value: int) -> str:
    """バイト数を人間が読みやすい形式にフォーマット"""
    size = float(bytes_value)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"

def load_config_file(filename: str) -> Dict[str, Any]:
    """設定ファイルを読み込み"""
    if not os.path.exists(filename):
        return {}
    
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ 設定ファイル読み込みエラー: {e}")
        return {}

def save_config_file(filename: str, config: Dict[str, Any]) -> bool:
    """設定ファイルを保存"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ 設定ファイル保存エラー: {e}")
        return False

def is_valid_port(port: int) -> bool:
    """ポート番号の有効性をチェック"""
    return 1 <= port <= 65535

def get_network_io_stats() -> Dict[str, Any]:
    """ネットワークI/O統計を取得"""
    try:
        io_counters = psutil.net_io_counters()
        return {
            'bytes_sent': io_counters.bytes_sent,
            'bytes_recv': io_counters.bytes_recv,
            'packets_sent': io_counters.packets_sent,
            'packets_recv': io_counters.packets_recv,
            'errin': io_counters.errin,
            'errout': io_counters.errout,
            'dropin': io_counters.dropin,
            'dropout': io_counters.dropout
        }
    except Exception as e:
        return {'error': f'ネットワークI/O統計取得エラー: {str(e)}'}

def get_disk_io_stats() -> Dict[str, Any]:
    """ディスクI/O統計を取得"""
    try:
        io_counters = psutil.disk_io_counters()
        if io_counters:
            return {
                'read_count': io_counters.read_count,
                'write_count': io_counters.write_count,
                'read_bytes': io_counters.read_bytes,
                'write_bytes': io_counters.write_bytes,
                'read_time': io_counters.read_time,
                'write_time': io_counters.write_time
            }
        return {}
    except Exception as e:
        return {'error': f'ディスクI/O統計取得エラー: {str(e)}'}

def clear_ip_cache():
    """IPキャッシュをクリア"""
    global _global_ip_cache
    _global_ip_cache = {
        'ip': None,
        'last_update': None,
        'cache_duration': 300
    }
    
def get_process_info() -> Dict[str, Any]:
    """現在のプロセス情報を取得"""
    try:
        process = psutil.Process()
        return {
            'pid': process.pid,
            'name': process.name(),
            'status': process.status(),
            'cpu_percent': process.cpu_percent(),
            'memory_info': {
                'rss': process.memory_info().rss,
                'vms': process.memory_info().vms
            },
            'create_time': datetime.fromtimestamp(process.create_time()).isoformat(),
            'num_threads': process.num_threads()
        }
    except Exception as e:
        return {'error': f'プロセス情報取得エラー: {str(e)}'}

# --- Bot起動時刻のメモリ記録 ---
_bot_start_time: Optional[datetime] = None

def set_bot_start_time(start_time: Optional[datetime] = None):
    """Botの起動時刻をグローバル変数に記録する（明示的に呼び出し）"""
    global _bot_start_time
    if start_time is None:
        start_time = datetime.now()
    _bot_start_time = start_time
    return _bot_start_time

def get_bot_start_time() -> Optional[datetime]:
    """グローバル変数からBotの起動時刻を取得"""
    global _bot_start_time
    return _bot_start_time



def get_auto_stop_time(start_time: Optional[datetime] = None) -> datetime:
    """Bot起動時刻からランダムで24時～30時間後の自動停止時刻を返す"""
    if start_time is None:
        try:
            start_time = get_bot_start_time()
        except Exception:
            start_time = None
        if start_time is None:
            start_time = datetime.now()
    hours = 24 + random.randint(0, 6)
    stop_time = start_time + timedelta(hours=hours)
    return stop_time