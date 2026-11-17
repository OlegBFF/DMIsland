"""Win32-хелперы: автозапуск, один экземпляр, полноэкранные окна, индикаторы приватности, рабочая область."""
import ctypes
import json
import os
import sys
import ctypes.wintypes
from pathlib import Path
from core.constants import RUN_KEY, STATE_PATH


def is_win_light():
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
        return winreg.QueryValueEx(k, 'AppsUseLightTheme')[0] == 1
    except Exception:
        return False


_SPI_GETWORKAREA, _SPI_SETWORKAREA, _SPIF_SENDCHANGE = 0x0030, 0x002F, 0x0002


def _get_workarea():
    """Рабочая область основного монитора в физических пикселях: (left, top, right, bottom) или None."""
    try:
        r = ctypes.wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
            return (r.left, r.top, r.right, r.bottom)
    except Exception:
        pass
    return None


def _set_workarea(rect):
    try:
        r = ctypes.wintypes.RECT(*rect)
        return bool(ctypes.windll.user32.SystemParametersInfoW(_SPI_SETWORKAREA, 0, ctypes.byref(r), _SPIF_SENDCHANGE))
    except Exception:
        return False


class WorkAreaGuard:
    """Резервирует полосу сверху экрана и гарантированно возвращает ИСХОДНУЮ рабочую область Windows.

    Раньше при выходе область выставлялась в «весь экран», и панель задач начинала перекрывать окна.
    Теперь исходный прямоугольник запоминается (и пишется в state.json), а при выходе/смене режима/после
    аварийного завершения восстанавливается — но только если область не успели изменить снаружи.
    """

    def __init__(s, state_path, getter=None, setter=None):
        s.path = Path(state_path)
        s._get = getter or _get_workarea
        s._set = setter or _set_workarea
        s._orig = None
        s._applied = None

    def _save(s):
        try:
            s.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = s.path.with_suffix('.tmp')
            tmp.write_text(json.dumps({'orig': s._orig, 'applied': s._applied}), 'utf-8')
            os.replace(tmp, s.path)
        except OSError:
            pass

    def _forget(s):
        s._orig = s._applied = None
        try:
            s.path.unlink(missing_ok=True)
        except OSError:
            pass

    def recover(s):
        """Вызывать при старте: если прошлый запуск упал и оставил урезанную область — вернуть её."""
        try:
            st = json.loads(s.path.read_text('utf-8'))
            orig, applied = tuple(st['orig']), tuple(st['applied'])
        except (OSError, ValueError, KeyError, TypeError):
            return False
        cur = s._get()
        ok = False
        if cur is not None and tuple(cur) == applied:
            ok = bool(s._set(orig))
        try:
            s.path.unlink(missing_ok=True)
        except OSError:
            pass
        return ok

    def reserve(s, top_px: int) -> bool:
        cur = s._get()
        if cur is None:
            return False
        cur = tuple(cur)
        if s._orig is None:
            s._orig = cur
        elif s._applied is not None and cur != s._applied and cur != s._orig:
            s._orig = cur                              # область изменили снаружи (панель задач, разрешение) — берём её как исходную
        l, t, r, b = s._orig
        new = (l, t + max(0, int(top_px)), r, b)
        s._applied = new
        s._save()                                      # сначала пишем состояние, потом меняем систему
        return True if cur == new else bool(s._set(new))

    def restore(s) -> bool:
        if s._orig is None:
            return False
        cur = s._get()
        ok = True
        if cur is not None and s._applied is not None and tuple(cur) == tuple(s._applied):
            ok = bool(s._set(s._orig))
        s._forget()
        return ok


WORKAREA = WorkAreaGuard(STATE_PATH)


def set_workarea_reserve(reserve_top_px: int):
    """reserve_top_px > 0 — зарезервировать полосу сверху (физические пиксели); 0 — вернуть исходную область."""
    if reserve_top_px > 0:
        WORKAREA.reserve(reserve_top_px)
    else:
        WORKAREA.restore()


class _MONITORINFOEX(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.wintypes.DWORD), ('rcMonitor', ctypes.wintypes.RECT),
                ('rcWork', ctypes.wintypes.RECT), ('dwFlags', ctypes.wintypes.DWORD),
                ('szDevice', ctypes.c_wchar * 32)]


def monitor_rect_px(device_name: str):
    """Физические координаты (left, top, right, bottom) монитора по имени QScreen (например \\\\.\\DISPLAY1)."""
    try:
        u = ctypes.WinDLL('user32', use_last_error=True)     # отдельный экземпляр: argtypes не пересекаются с остальным кодом
        found = []
        proc_t = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)

        def cb(hmon, hdc, lprc, data):
            mi = _MONITORINFOEX()
            mi.cbSize = ctypes.sizeof(mi)
            if u.GetMonitorInfoW(ctypes.c_void_p(hmon), ctypes.byref(mi)) and mi.szDevice == device_name:
                r = mi.rcMonitor
                found.append((r.left, r.top, r.right, r.bottom))
            return 1
        u.EnumDisplayMonitors(None, None, proc_t(cb), 0)
        return found[0] if found else None
    except Exception:
        return None


def is_foreground_maximized_top() -> bool:
    """Проверяет, развёрнуто ли активное окно во весь экран у верхней кромки (например, браузер с вкладками)."""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        if not hwnd:
            return False
        if ctypes.windll.user32.IsZoomed(hwnd):
            return True
        r = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
        return r.top <= 4 and (r.right - r.left) > 900
    except Exception:
        return False


# ==================== WIN32-ХЕЛПЕРЫ: АВТОЗАПУСК, ОДИН ЭКЗЕМПЛЯР, FULLSCREEN, ПРИВАТНОСТЬ ====================
def autostart_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, 'IslandPro')
            return True
    except OSError:
        return False


def set_autostart(on: bool) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                exe = sys.executable
                if os.environ.get('ISLAND_LAUNCHER_CMD'):
                    cmd = os.environ['ISLAND_LAUNCHER_CMD']          # запущены через лаунчер — автозапуск тоже через него (с логами)
                elif getattr(sys, 'frozen', False):
                    cmd = f'"{exe}"'
                else:
                    if exe.lower().endswith('python.exe'):
                        pw = exe[:-10] + 'pythonw.exe'
                        exe = pw if os.path.exists(pw) else exe
                    main_py = Path(__file__).resolve().parent.parent / 'main.py'   # раньше здесь был сам win32.py — автозапуск ничего не запускал
                    cmd = f'"{exe}" "{main_py}"'
                winreg.SetValueEx(k, 'IslandPro', 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(k, 'IslandPro')
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False

_MUTEX = None


def acquire_single_instance() -> bool:
    """False, если Island уже запущен (защита от двойного запуска)."""
    global _MUTEX
    try:
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        _MUTEX = k32.CreateMutexW(None, False, 'Local\\IslandPro.SingleInstance')
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    except Exception:
        return True


class _MONITORINFO(ctypes.Structure):
    _fields_ = [('cbSize', ctypes.wintypes.DWORD), ('rcMonitor', ctypes.wintypes.RECT),
                ('rcWork', ctypes.wintypes.RECT), ('dwFlags', ctypes.wintypes.DWORD)]

_FS_SKIP = {'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'}


def foreground_fullscreen(own_hwnd: int = 0) -> bool:
    """True, если активное окно (игра, видео, презентация) занимает весь монитор острова."""
    try:
        u = ctypes.windll.user32
        u.GetForegroundWindow.restype = ctypes.c_void_p
        u.MonitorFromWindow.restype = ctypes.c_void_p
        u.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.wintypes.DWORD]
        u.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]
        hwnd = u.GetForegroundWindow()
        if not hwnd or hwnd == own_hwnd:
            return False
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(ctypes.c_void_p(hwnd), cls, 64)
        if cls.value in _FS_SKIP:
            return False
        style = u.GetWindowLongW(ctypes.c_void_p(hwnd), -16) & 0xFFFFFFFF     # GWL_STYLE
        if (style & 0xC00000) == 0xC00000:
            return False                              # есть заголовок (WS_CAPTION) — обычное развёрнутое окно, не fullscreen
        r = ctypes.wintypes.RECT()
        u.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r))
        mon = u.MonitorFromWindow(hwnd, 2)            # MONITOR_DEFAULTTONEAREST
        if own_hwnd and mon != u.MonitorFromWindow(own_hwnd, 2):
            return False                              # полноэкранное окно на другом мониторе
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        if not u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return False
        m = mi.rcMonitor
        t = 2
        return (abs(r.left - m.left) <= t and abs(r.top - m.top) <= t
                and abs(r.right - m.right) <= t and abs(r.bottom - m.bottom) <= t)
    except Exception:
        return False


def _consent_in_use(cap: str) -> str:
    """Имя приложения, которое прямо сейчас использует микрофон/камеру (по данным CapabilityAccessManager)."""
    import winreg
    base = rf'Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\{cap}'
    for sub in ('', r'\NonPackaged'):
        try:
            root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, base + sub)
        except OSError:
            continue
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            if name == 'NonPackaged':
                continue
            try:
                with winreg.OpenKey(root, name) as k:
                    start = winreg.QueryValueEx(k, 'LastUsedTimeStart')[0]
                    stop = winreg.QueryValueEx(k, 'LastUsedTimeStop')[0]
                if start and not stop:
                    nice = name.split('#')[-1] if '#' in name else name.split('_')[0]
                    return Path(nice).stem.split('.')[-1] if nice.lower().endswith('.exe') else nice
            except OSError:
                continue
    return ''


# ==================== ФОКУС ПО ТРЕБОВАНИЮ, ПРОЦЕСС НА ПЕРЕДНЕМ ПЛАНЕ, МАСШТАБ ====================
_PRIV = {}


def _dlls():
    """Отдельные экземпляры user32/kernel32 с точными argtypes: не пересекаются с остальным кодом, безопасны на 64 бит."""
    if not _PRIV:
        u = ctypes.WinDLL('user32', use_last_error=True)
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        H, D = ctypes.c_void_p, ctypes.wintypes.DWORD
        u.GetForegroundWindow.restype = H
        u.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(D)]
        u.GetWindowThreadProcessId.restype = D
        u.AttachThreadInput.argtypes = [D, D, ctypes.wintypes.BOOL]
        u.SetForegroundWindow.argtypes = [H]
        u.BringWindowToTop.argtypes = [H]
        u.GetWindowLongPtrW.argtypes = [H, ctypes.c_int]
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.SetWindowLongPtrW.argtypes = [H, ctypes.c_int, ctypes.c_ssize_t]
        u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.SetWindowPos.argtypes = [H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        u.MonitorFromPoint.argtypes = [ctypes.wintypes.POINT, D]
        u.MonitorFromPoint.restype = H
        u.GetMonitorInfoW.argtypes = [H, ctypes.POINTER(_MONITORINFOEX)]
        k.OpenProcess.argtypes = [D, ctypes.wintypes.BOOL, D]
        k.OpenProcess.restype = H
        k.CloseHandle.argtypes = [H]
        k.QueryFullProcessImageNameW.argtypes = [H, D, ctypes.c_wchar_p, ctypes.POINTER(D)]
        k.GetCurrentThreadId.restype = D
        _PRIV.update(u=u, k=k)
    return _PRIV['u'], _PRIV['k']


_GWL_EXSTYLE, _WS_EX_NOACTIVATE = -20, 0x08000000


def set_no_activate(hwnd: int, on: bool):
    """WS_EX_NOACTIVATE: клики по острову не крадут фокус у других окон. Выключается на время набора текста."""
    try:
        u, _ = _dlls()
        st = u.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
        st = (st | _WS_EX_NOACTIVATE) if on else (st & ~_WS_EX_NOACTIVATE)
        u.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, st)
        u.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)   # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED
    except Exception:
        pass


def force_foreground(hwnd: int) -> int:
    """Делает окно активным (Windows разрешает это процессу, только что получившему ввод) и возвращает прежнее активное окно."""
    try:
        u, k = _dlls()
        prev = u.GetForegroundWindow() or 0
        cur, fg = k.GetCurrentThreadId(), u.GetWindowThreadProcessId(prev, None) if prev else 0
        attached = bool(fg and fg != cur and u.AttachThreadInput(fg, cur, True))
        u.BringWindowToTop(hwnd)
        u.SetForegroundWindow(hwnd)
        if attached:
            u.AttachThreadInput(fg, cur, False)
        return int(prev)
    except Exception:
        return 0


def restore_foreground(hwnd: int):
    try:
        if hwnd:
            _dlls()[0].SetForegroundWindow(hwnd)
    except Exception:
        pass


def foreground_process_name() -> str:
    """Имя exe окна на переднем плане в нижнем регистре ('chrome.exe') или ''."""
    try:
        u, k = _dlls()
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return ''
        pid = ctypes.wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = k.OpenProcess(0x1000, False, pid.value)                  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ''
        try:
            buf, n = ctypes.create_unicode_buffer(520), ctypes.wintypes.DWORD(520)
            return os.path.basename(buf.value).lower() if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ''
        finally:
            k.CloseHandle(h)
    except Exception:
        return ''


def primary_logical_width():
    """Логическая ширина основного монитора (физическая / масштаб Windows) — до создания QApplication."""
    try:
        u, _ = _dlls()
        mon = u.MonitorFromPoint(ctypes.wintypes.POINT(0, 0), 1)       # MONITOR_DEFAULTTOPRIMARY
        mi = _MONITORINFOEX()
        mi.cbSize = ctypes.sizeof(mi)
        if not u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        width = mi.rcMonitor.right - mi.rcMonitor.left
        dx, dy = ctypes.c_uint(96), ctypes.c_uint(96)
        try:
            ctypes.windll.shcore.GetDpiForMonitor(ctypes.c_void_p(mon), 0, ctypes.byref(dx), ctypes.byref(dy))
        except Exception:
            pass
        return int(width * 96 / max(dx.value, 96))
    except Exception:
        return None


def send_ctrl_v():
    """Нажимает Ctrl+V в активном окне (для вставки быстрого ответа)."""
    try:
        ev = ctypes.windll.user32.keybd_event
        ev(0x11, 0, 0, 0)
        ev(0x56, 0, 0, 0)
        ev(0x56, 0, 2, 0)
        ev(0x11, 0, 2, 0)
    except Exception:
        pass
