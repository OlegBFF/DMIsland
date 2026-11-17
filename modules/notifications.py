"""События устройств (USB, зарядка, наушники), индикаторы приватности и всплывающие уведомления."""
import ctypes
import os
import psutil
import threading
import time
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor
from core.utils import log
from core.win32 import _consent_in_use


class DeviceWatcher(QObject):
    """Фоновый поток: подключение флешек, зарядки, наушников + индикаторы использования микрофона/камеры."""
    event = Signal(str, str, str)       # kind (usb|charger|headphones|audio|off), title, sub
    privacy = Signal(str, str)          # (приложение с микрофоном, приложение с камерой)

    HEAD_WORDS = ('head', 'науш', 'buds', 'airpods', 'bluetooth', 'wh-', 'wf-', 'gaming', 'hands-free')

    def __init__(s):
        super().__init__()
        s._stop = False
        s._enum = None
        threading.Thread(target=s._run, name='island-devices', daemon=True).start()

    @staticmethod
    def _drives():
        res = {}
        try:
            sysdrive = os.getenv('SystemDrive', 'C:').upper()
            for part in psutil.disk_partitions(all=False):
                mp = part.mountpoint
                if mp.upper().startswith(sysdrive) or 'cdrom' in part.opts.lower():
                    continue
                res[mp] = part
        except Exception:
            pass
        return res

    @staticmethod
    def _label(mp: str) -> str:
        try:
            buf = ctypes.create_unicode_buffer(261)
            if ctypes.windll.kernel32.GetVolumeInformationW(mp, buf, 261, None, None, None, None, 0) and buf.value:
                return f"{buf.value} ({mp.rstrip(chr(92))})"
        except Exception:
            pass
        return mp.rstrip('\\')

    @staticmethod
    def _plugged():
        try:
            b = psutil.sensors_battery()
            return (b.power_plugged, int(b.percent)) if b else (None, 0)
        except Exception:
            return None, 0

    def _audio(s):
        """Имена активных аудиоустройств; None, если прочитать не удалось (тогда событий «подключено» не будет)."""
        try:
            from system.audio_names import active_device_names, create_enumerator
            if s._enum is None:
                s._enum = create_enumerator()               # создаётся и живёт в потоке наблюдателя
            return set(active_device_names(s._enum).values())
        except Exception as ex:
            s._enum = None
            log(f"device watcher audio: {ex!r}")
            return None

    def _run(s):
        from system.util import com_gc, com_init_mta
        com_init_mta()
        drives, (plug, _), audio = s._drives(), s._plugged(), s._audio()
        last_priv, n = ('', ''), 0
        while not s._stop:
            time.sleep(1.2)
            n += 1
            if n % 8 == 0:
                com_gc()                                    # COM-мусор убираем в этом же потоке
            try:
                pv = (_consent_in_use('microphone'), _consent_in_use('webcam'))
                if pv != last_priv:
                    last_priv = pv
                    s.privacy.emit(*pv)

                if n % 2 == 0:
                    cur = s._drives()
                    for mp in cur.keys() - drives.keys():
                        try:
                            free = psutil.disk_usage(mp).total / 1e9
                            sub = f"Подключено · {free:.0f} ГБ"
                        except Exception:
                            sub = 'Подключено'
                        s.event.emit('usb', s._label(mp), sub)
                    for mp in drives.keys() - cur.keys():
                        s.event.emit('off', f"Диск {mp.rstrip(chr(92))}", 'Безопасно отключён')
                    drives = cur

                    p2, pct = s._plugged()
                    if p2 is not None and plug is not None and p2 != plug:
                        s.event.emit('charger', 'Зарядка подключена' if p2 else 'Зарядка отключена', f"Заряд {pct}%")
                    plug = p2

                if n % 3 == 0:
                    cur_a = s._audio()
                    if cur_a is not None and audio is not None:
                        for name in cur_a - audio:
                            kind = 'headphones' if any(w in name.lower() for w in s.HEAD_WORDS) else 'audio'
                            s.event.emit(kind, name[:34], 'Аудиоустройство подключено')
                        for name in audio - cur_a:
                            s.event.emit('off', name[:34], 'Аудиоустройство отключено')
                    if cur_a is not None:
                        audio = cur_a
            except Exception as ex:
                log(f"device watcher: {ex!r}")

# kind → (цвет, иконка) для тостов подключения устройств
DEV_STYLE = {'usb': ('#0a84ff', 'usb'), 'charger': ('#34c759', 'bolt'), 'headphones': ('#bf5af2', 'headphones'),
             'audio': ('#64d2ff', 'music'), 'off': ('#8e8e93', 'close')}


class NotificationsMixin:
    """Часть класса Island: NotificationsMixin."""

    # ==================== СОБЫТИЯ УСТРОЙСТВ И ПРИВАТНОСТЬ ====================
    def on_device_event(s, kind, title, sub):
        if not s.cfg.get('device_events', True):
            return
        s.record_system(title, sub)                      # событие попадает в историю уведомлений как системное
        if s.mode == 'open':
            return
        col, ic = DEV_STYLE.get(kind, DEV_STYLE['audio'])
        s.pop(title, sub, (QColor(col), ic), 4.2)

    def on_privacy(s, mic, cam):
        prev, s.priv = s.priv, (mic, cam)
        if getattr(s, 'cc', None) is not None:
            s.cc.set_privacy(mic, cam)
        if not s.cfg.get('privacy_dots', True) or s.mode == 'open':
            return
        if mic and not prev[0]:
            s.pop('Микрофон включён', mic, (QColor('#ff9f0a'), 'mic'), 2.6)
        elif cam and not prev[1]:
            s.pop('Камера включена', cam, (QColor('#30d158'), 'cam'), 2.6)

    def pop(s, title, sub='', ic=None, secs=3.2):
        if s.mode == 'notif':                              # пока на острове карточка уведомления, мелкие тосты её не перебивают
            return
        if s.mode == 'open' and s.chat_hold():             # в чате остров не сворачивается — тост показываем внутри чата
            col, name = ic if isinstance(ic, tuple) else (ic if isinstance(ic, QColor) else None, None)
            s.chat_toast(title, sub, col, secs, name if name in ('check', 'info', 'close', 'bell', 'chat', 'notes', 'voice') else 'check')
            return
        s.toast = (title, sub, ic)
        s.toast_t0 = time.time()
        s.toast_secs = max(secs, 0.5)
        s.until = s.toast_t0 + secs
        s.mode = 'toast'
        s.leave = 0
        s.anim_timer.setInterval(s.frame_ms_v)
