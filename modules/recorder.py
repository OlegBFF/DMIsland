"""Запись экрана: тонкая Qt-обёртка над RecorderEngine. Qt используется только здесь и только в главном потоке."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor
from core.constants import SHOTS_DIR
from core.win32 import monitor_rect_px
from modules.recorder_core import RecorderEngine


class ScreenRecorder(QObject):
    finished = Signal(str, str)           # путь к файлу ('' при ошибке), примечание

    def __init__(s):
        super().__init__()
        s.engine = None

    @property
    def recording(s) -> bool:
        return bool(s.engine and s.engine.recording)

    @property
    def start_t(s) -> float:
        return s.engine.start_t if s.engine else 0.0

    @staticmethod
    def _bbox(screen):
        """Физические пиксели монитора. Размеры и позицию берём из главного потока, поток записи Qt не видит."""
        r = monitor_rect_px(screen.name())
        if r:
            return r
        g, k = screen.geometry(), screen.devicePixelRatio()
        return (int(g.x() * k), int(g.y() * k), int((g.x() + g.width()) * k), int((g.y() + g.height()) * k))

    def start(s, screen, cfg):
        if s.recording:
            return
        fmt = 'gif' if cfg.get('rec_format') == 'gif' else 'mp4'
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        out = SHOTS_DIR / f"Rec_{datetime.now():%Y%m%d_%H%M%S}.{fmt}"
        max_s = int(cfg.get('rec_gif_sec', 20)) if fmt == 'gif' else int(cfg.get('rec_max_min', 30)) * 60
        s.engine = RecorderEngine(out, fmt, int(cfg.get('fps', 30)), s._bbox(screen), lambda p, n: s.finished.emit(p, n),
                                  sys_audio=bool(cfg.get('rec_audio_system', True)), mic_audio=bool(cfg.get('rec_audio_mic', False)),
                                  max_seconds=max_s, gif_mem_mb=int(cfg.get('rec_gif_mem_mb', 64)))
        s.engine.start()

    def stop(s):
        if s.engine:
            s.engine.stop()

    def shutdown(s, timeout=20):
        """При выходе из приложения: дожидаемся, пока файл будет корректно закрыт."""
        if s.engine and s.engine._thread and s.engine._thread.is_alive():
            s.engine.stop()
            s.engine.join(timeout)


class RecorderMixin:
    """Часть класса Island: RecorderMixin."""

    def toggle_record(s):
        if s.recorder.recording:
            s.recorder.stop()
            s.pop('Запись экрана', 'Сохраняю файл…', (QColor('#ff9f0a'), 'rec'), 3.0)
        else:
            s.mode = 'idle'
            s.recorder.start(s.get_target_screen(), s.cfg)

    def on_rec_finished(s, path, note=''):
        if path and Path(path).exists():
            s.clips.add_file_item('file', path, f"Запись {Path(path).name}", owned=False)
            s.refresh_clip()
            s.pop('Запись сохранена', note or Path(path).name, (QColor('#34c759') if not note else QColor('#ff9f0a'), 'rec'), 5.0)
        else:
            s.pop('Запись экрана', note or 'Не удалось сохранить запись', (QColor('#ff453a'), 'rec'), 5.0)
