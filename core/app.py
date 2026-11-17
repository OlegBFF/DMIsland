"""Запуск приложения."""
import atexit
import ctypes
import os
import sys
import traceback
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from core import diagnostics
from core.config import load_cfg
from core.constants import APP_NAME, APP_PUBLISHER, LOG_PATH
from core.notif_rules import resolve_ui_scale
from core.utils import log
from core.win32 import WORKAREA, acquire_single_instance, primary_logical_width
from ui.island import Island


def run():
    """Точка входа: логирование ошибок, один экземпляр, QApplication, главное окно."""
    diagnostics.install()
    diagnostics.log_environment()

    if not acquire_single_instance():          # второй запуск молча завершается
        sys.exit(0)
    WORKAREA.recover()                         # прошлый запуск мог упасть и оставить урезанную рабочую область
    atexit.register(WORKAREA.restore)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('IslandPro.Desktop')
    except Exception:
        pass

    # Масштаб всего интерфейса: «Авто» подбирается по логической ширине монитора; должен быть задан до QApplication
    try:
        k = resolve_ui_scale(load_cfg().get('ui_scale', 'auto'), primary_logical_width())
        if abs(k - 1.0) > 0.01:
            os.environ['QT_SCALE_FACTOR'] = f"{k:.2f}"
    except Exception as ex:
        log(f"ui_scale: {ex!r}")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_PUBLISHER)
    app.setQuitOnLastWindowClosed(False)
    f = QFont()
    f.setFamilies(['Segoe UI Variable Text', 'Segoe UI'])
    f.setPixelSize(13)
    f.setHintingPreference(QFont.PreferNoHinting)
    app.setFont(f)
    try:
        isl = Island()
    except BaseException:
        text = traceback.format_exc()
        log('STARTUP FAILED\n' + text)
        sys.stderr and sys.stderr.write(text)
        _message_box(f"Не удалось запустить остров.\n\n{text.strip().splitlines()[-1]}\n\nПодробности: {LOG_PATH}")
        sys.exit(1)
    sys.exit(app.exec())


def _message_box(text):
    """Окно с ошибкой: под pythonw консоли нет, и без него падение выглядело бы как «ничего не произошло»."""
    try:
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
    except Exception:
        pass
