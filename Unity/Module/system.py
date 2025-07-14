# Unity/Module/system.py
"""
SystemBaseの実装: setTimeout, clearTimeout, setInterval, clearInterval, run, runAsync
"""
from Unity.Base import SystemBase, unity_registry
import threading
import time
import asyncio

class System(SystemBase):
    def __init__(self):
        self._timers = {}
        self._intervals = {}
        self._timer_id = 0
        self._lock = threading.Lock()
    def setTimeout(self, callback, delay, *args, **kwargs):
        with self._lock:
            self._timer_id += 1
            tid = self._timer_id
        def timer_func():
            time.sleep(delay)
            callback(*args, **kwargs)
        t = threading.Thread(target=timer_func, daemon=True)
        t.start()
        self._timers[tid] = t
        return tid
    def clearTimeout(self, tid):
        if tid in self._timers:
            del self._timers[tid]
    def setInterval(self, callback, interval, *args, **kwargs):
        with self._lock:
            self._timer_id += 1
            tid = self._timer_id
        def interval_func():
            while tid in self._intervals:
                time.sleep(interval)
                callback(*args, **kwargs)
        self._intervals[tid] = True
        t = threading.Thread(target=interval_func, daemon=True)
        t.start()
        self._timers[tid] = t
        return tid
    def clearInterval(self, tid):
        if tid in self._intervals:
            del self._intervals[tid]
        if tid in self._timers:
            del self._timers[tid]
    def run(self, func, *args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=True)
        t.start()
        return t
    def runAsync(self, coro):
        loop = asyncio.get_event_loop()
        return loop.create_task(coro)

# systemインスタンスを登録
unity_registry.register_system(System())
