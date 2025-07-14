# Unity/Module/discord_event.py
"""
DiscordイベントをUnity afterEventに中継するモジュール
"""
from Unity.Base import unity_registry

def relay_discord_event(event_name, *args, **kwargs):
    """DiscordイベントをUnity afterEventに転送"""
    unity_registry.events.fire(event_name, *args, **kwargs)

# 例: Bot側で on_message などのイベント時に relay_discord_event("message", message) を呼ぶことで
# Module側で afterEvent.subscribe("message", ...) で購読できる
