"""Мелкие помощники для системных контроллеров. Импортируется и вне Windows (всё Windows-специфичное — внутри функций)."""
import importlib
import os
import re
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def wr(module: str):
    """Модуль WinRT-проекции: winrt.* (новый пакет) или winsdk.* (старый)."""
    try:
        return importlib.import_module('winrt.' + module)
    except ImportError:
        return importlib.import_module('winsdk.' + module)


def com_init_mta() -> bool:
    """COM в многопоточной квартире (MTA) для текущего потока. Все фоновые COM-потоки острова работают в MTA:
    указатели Core Audio можно безопасно освободить из любого потока, и они не ждут цикла сообщений."""
    try:
        import comtypes
    except Exception:
        return False
    try:
        comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
    except OSError:                                         # S_FALSE / RPC_E_CHANGED_MODE: поток уже инициализирован
        pass
    except Exception:
        return False
    return True


def com_gc():
    """Собрать мусор прямо в COM-потоке. Освобождение COM-указателей (comtypes.__del__) должно происходить в потоке с
    инициализированным COM, а автоматический сборщик может сработать в любом (погода, сеть, …) — отсюда редкие
    access violation. Циклический мусор с указателями убираем сами, пока поток ещё «свой»."""
    import gc
    gc.collect()


def run_hidden(cmd, timeout=8) -> str:
    """Запуск консольной утилиты без окна; вывод в кодировке консоли (netsh отдаёт OEM-кодовую страницу)."""
    kw = {'creationflags': CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    res = subprocess.run(cmd, capture_output=True, timeout=timeout, **kw)
    enc = 'oem' if sys.platform == 'win32' else 'utf-8'
    return (res.stdout or b'').decode(enc, errors='replace')


_SETTINGS_RX = re.compile(r'^ms-settings:[a-z0-9-]+$')


def open_settings(uri: str) -> bool:
    """Открывает страницу параметров Windows (только ms-settings:, без произвольных URI)."""
    if not _SETTINGS_RX.match(uri):
        return False
    try:
        os.startfile(uri)
        return True
    except (OSError, AttributeError):
        return False


def run_async(coro):
    """Выполнить корутину WinRT в текущем (рабочем) потоке."""
    import asyncio
    return asyncio.run(coro)
