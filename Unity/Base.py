# Unity/Base.py
"""
Unityの型・基盤・登録関数群 (Base)
- 型定義
- イベント/システム/モジュール登録API
- 共通の抽象化
"""
import threading
import asyncio
from typing import Callable, Dict, Any, List, Optional, Type
import time

# --- 型定義 ---
class EventType:
    def __init__(self, name: str):
        self.name = name
        self._subscribers: List[Callable] = []
    def subscribe(self, callback: Callable):
        if callback not in self._subscribers:
            self._subscribers.append(callback)
        return callback
    def unsubscribe(self, callback: Callable):
        if callback in self._subscribers:
            self._subscribers.remove(callback)
    def fire(self, *args, **kwargs):
        for cb in self._subscribers:
            cb(*args, **kwargs)

class afterEvent:
    EventType = EventType
    _events: Dict[str, EventType] = {}
    @classmethod
    def get_event(cls, name: str) -> EventType:
        if name not in cls._events:
            cls._events[name] = EventType(name)
        return cls._events[name]
    @classmethod
    def subscribe(cls, name: str, callback: Callable):
        return cls.get_event(name).subscribe(callback)
    @classmethod
    def unsubscribe(cls, name: str, callback: Callable):
        return cls.get_event(name).unsubscribe(callback)
    @classmethod
    def fire(cls, name: str, *args, **kwargs):
        return cls.get_event(name).fire(*args, **kwargs)

import threading
import asyncio
from threading import Thread
from asyncio import Task

class SystemBase:
    def setTimeout(self, callback: Callable, delay: float, *args, **kwargs) -> int: ...
    def clearTimeout(self, tid: int) -> None: ...
    def setInterval(self, callback: Callable, interval: float, *args, **kwargs) -> int: ...
    def clearInterval(self, tid: int) -> None: ...
    def run(self, func: Callable, *args, **kwargs) -> Thread: ...
    def runAsync(self, coro) -> Task: ...

# --- 登録API ---
class UnityRegistry:
    """モジュール・システム・イベント等の登録管理"""
    def __init__(self):
        self.system: Optional[SystemBase] = None
        self.modules: Dict[str, Any] = {}
        self.events = afterEvent
    def register_system(self, system: SystemBase):
        self.system = system
    def register_module(self, name: str, module: Any):
        self.modules[name] = module
    def get_module(self, name: str) -> Any:
        return self.modules.get(name)

# --- シングルトン ---
unity_registry = UnityRegistry()
