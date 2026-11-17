"""Диагностика падений: всё, что раньше исчезало в консоли (или под pythonw — вообще нигде), попадает в %APPDATA%\\Island.

  island.log  — исключения Python (главный и фоновые потоки), «Exception ignored», предупреждения Qt/Python
  crash.log   — нативные падения (access violation и т. п.): faulthandler печатает стеки всех потоков

Однотипные сообщения пишутся первые 3 раза, потом считаются — лог не раздувается лавиной (как было с pycaw).
"""
import faulthandler
import sys
import threading
import traceback
import warnings
from datetime import datetime
from core.constants import APP_NAME, APP_VER, CRASH_PATH
from core.utils import log

_seen = {}
_LIMIT = 3
_crash_file = None


def _once(key: str) -> bool:
    n = _seen[key] = _seen.get(key, 0) + 1
    if n == _LIMIT + 1:
        log(f"(повторяется, дальше не пишу) {key[:120]}")
    return n <= _LIMIT


def _to_stderr(text: str):
    try:
        if sys.stderr is not None:
            sys.stderr.write(text if text.endswith('\n') else text + '\n')
            sys.stderr.flush()
    except Exception:
        pass


def _excepthook(t, v, tb):
    text = ''.join(traceback.format_exception(t, v, tb))
    log('UNCAUGHT\n' + text)
    _to_stderr(text)


def _thread_hook(args):
    if args.exc_type is SystemExit:
        return
    name = args.thread.name if args.thread else '?'
    text = ''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    log(f"THREAD {name}\n{text}")
    _to_stderr(f"[thread {name}]\n{text}")


def _unraisable_hook(u):
    """«Exception ignored in …»: чаще всего comtypes.__del__ при освобождении COM-указателя."""
    where = getattr(u.object, '__qualname__', None) or repr(u.object)[:80]
    msg = f"{type(u.exc_value).__name__}: {u.exc_value}"
    key = f"unraisable {where}: {msg}"
    if _once(key):
        log(f"Exception ignored in {where}: {msg}")


def _showwarning(message, category, filename, lineno, file=None, line=None):
    key = f"{category.__name__}: {str(message)[:100]}"
    if _once('warn ' + key):
        log(f"WARNING {key} ({filename}:{lineno})")


def _qt_handler(mode, ctx, message):
    try:
        lvl = int(getattr(mode, 'value', mode))
    except Exception:
        lvl = 1
    if lvl < 1:                                   # QtDebugMsg — не интересно
        return
    if _once(f"qt{lvl} {message[:100]}"):
        log(f"Qt[{lvl}] {message}")


def install():
    """Вызывать первым делом в run(), до создания QApplication."""
    global _crash_file
    sys.excepthook = _excepthook
    threading.excepthook = _thread_hook
    sys.unraisablehook = _unraisable_hook
    warnings.showwarning = _showwarning
    warnings.filterwarnings('ignore', message=r'COMError attempting to get property')   # шум pycaw (см. system/audio_names.py)
    try:
        CRASH_PATH.parent.mkdir(parents=True, exist_ok=True)
        if CRASH_PATH.exists() and CRASH_PATH.stat().st_size > 256_000:
            CRASH_PATH.write_text('', 'utf-8')
        _crash_file = CRASH_PATH.open('a', encoding='utf-8', buffering=1)
        _crash_file.write(f"\n===== запуск {datetime.now():%Y-%m-%d %H:%M:%S} =====\n")
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception as ex:
        log(f"faulthandler: {ex!r}")
    try:
        from PySide6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(_qt_handler)
    except Exception as ex:
        log(f"qt handler: {ex!r}")


def log_environment():
    """Версии библиотек в начале лога: по ним сразу видно, чем отличается чужая машина."""
    import platform
    from importlib import metadata
    parts = [f"{APP_NAME} {APP_VER}", f"Python {platform.python_version()}", platform.platform()]
    for pkg in ('PySide6', 'pycaw', 'comtypes', 'psutil', 'pyaudiowpatch', 'winrt-runtime', 'mss', 'numpy'):
        try:
            parts.append(f"{pkg} {metadata.version(pkg)}")
        except Exception:
            parts.append(f"{pkg} —")
    log('START ' + ' | '.join(parts))
