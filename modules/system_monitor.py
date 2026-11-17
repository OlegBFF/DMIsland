"""Состояние системы: батарея, действия питания, тема Windows."""
import psutil
import subprocess
import time
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from core.utils import log
from system import winmode


class SystemMixin:
    """Часть класса Island: SystemMixin."""

    # ==================== ПОГОДА, АУДИО И IN-MEMORY OCR/QR ====================
    def slow(s):
        s.bat = psutil.sensors_battery()
        s.clip_maintenance()

    def risky(s, b, label, cmd):
        if getattr(b, 'armed', 0) > time.time():
            subprocess.Popen(cmd)
        else:
            b.armed = time.time() + 3
            b.setText('Подтвердить?')
            QTimer.singleShot(3000, lambda: b.setText(label))

    def toggle_win_theme(s):
        """Переключает светлый/тёмный режим Windows (система и приложения вместе)."""
        try:
            light = winmode.toggle_both()
            s.sync_win_theme()
            s.pop('Режим Windows', 'Светлый' if light else 'Тёмный', (QColor('#0a84ff'), 'sun' if light else 'moon'))
        except Exception as ex:
            log(f"toggle_win_theme: {ex!r}")

    def sync_win_theme(s):
        """Если тема острова «Как в Windows» — перекрашиваем остров."""
        s.update_theme_flag()
        s.refresh_accent()
        s.restyle()
