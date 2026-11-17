"""Рабочий поток с очередью команд и периодическим опросом состояния. Без Qt.

Команды с одинаковым key вытесняют друг друга (ползунок громкости не копит сотни вызовов COM),
после каждой команды состояние перечитывается сразу — интерфейс показывает реальное, а не ожидаемое.
"""
import threading
import time
from collections import OrderedDict
from core.utils import log


class Worker:
    def __init__(s, name, poll=None, interval=1.0, init=None, on_result=None, on_error=None, gc_every=0):
        s.name, s.poll, s.interval, s.init = name, poll, interval, init
        s.gc_every, s._ticks = gc_every, 0               # gc_every > 0: каждые N опросов/команд собирать мусор в этом потоке
        s.on_result = on_result or (lambda r: None)
        s.on_error = on_error or (lambda name, ex, kind: log(f"worker {name} {kind}: {ex!r}"))
        s._jobs = OrderedDict()
        s._lock = threading.Lock()
        s._wake = threading.Event()
        s._stop = False
        s._active = False
        s._counter = 0
        s._thread = threading.Thread(target=s._run, name=f"island-{name}", daemon=True)

    def start(s):
        s._thread.start()

    def stop(s):
        s._stop = True
        s._wake.set()

    def set_active(s, on: bool):
        if on != s._active:
            s._active = on
            s._wake.set()

    def refresh(s):
        s._wake.set()
        with s._lock:
            s._force = True

    _force = False

    def submit(s, fn, key=None):
        """Поставить команду в очередь. fn() может вернуть dict — он уйдёт в on_result."""
        with s._lock:
            if key is None:
                s._counter += 1
                key = f"#{s._counter}"
            s._jobs.pop(key, None)
            s._jobs[key] = fn
            s._force = True
        s._wake.set()

    def _pop(s):
        with s._lock:
            if not s._jobs:
                return None
            return s._jobs.popitem(last=False)[1]

    def _emit(s, res):
        if res:
            try:
                s.on_result(res)
            except Exception as ex:
                log(f"worker {s.name} on_result: {ex!r}")

    def _collect(s):
        if s.gc_every:
            s._ticks += 1
            if s._ticks % s.gc_every == 0:
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass

    def _run(s):
        try:
            if s.init:
                s.init()
        except Exception as ex:
            log(f"worker {s.name} init: {ex!r}")
        next_poll = 0.0
        while not s._stop:
            job = s._pop()
            if job is not None:
                try:
                    s._emit(job())
                except Exception as ex:
                    s.on_error(s.name, ex, 'job')
                next_poll = 0.0                     # перечитать состояние сразу после команды
                s._collect()
                continue
            now = time.monotonic()
            with s._lock:
                force, s._force = s._force, False
            if s.poll and (force or (s._active and now >= next_poll)):
                try:
                    s._emit(s.poll())
                except Exception as ex:
                    s.on_error(s.name, ex, 'poll')
                next_poll = time.monotonic() + s.interval
                s._collect()
            timeout = max(0.02, next_poll - time.monotonic()) if (s._active and s.poll) else 1.0
            s._wake.wait(min(timeout, 1.0))
            s._wake.clear()
