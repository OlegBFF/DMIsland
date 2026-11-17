"""Позиционирование окна, интеграция с окнами Windows, показ и скрытие."""
import ctypes
from PySide6.QtGui import QColor, QGuiApplication
from core.constants import CH, H, W
from core.utils import clamp
from core.win32 import is_foreground_maximized_top, set_workarea_reserve


class WindowMixin:
    """Часть класса Island: WindowMixin."""

    def sync_visibility(s):
        want = not (s.user_hidden or s.fs or s.app_hidden)
        if want != s.isVisible():
            s.setVisible(want)

    def toggle_hidden(s):
        s.user_hidden = not s.user_hidden
        s.sync_visibility()

    def set_transparent_input(s, pass_clicks: bool):
        try:
            hwnd = int(s.winId())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_LAYERED = 0x00080000
            st = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if pass_clicks:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, st | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            else:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, st & ~WS_EX_TRANSPARENT)
        except Exception:
            pass

    def apply_window_integration(s):
        hwnd = int(s.winId())
        aff = 0x00 if s.cfg.get('show_in_capture') else 0x11
        try:
            ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, aff)
        except Exception:
            pass

        fit = s.cfg.get('window_fit', 'smart_dodge')
        scr = s.get_target_screen()
        if fit == 'workarea' and scr is QGuiApplication.primaryScreen():
            set_workarea_reserve(int(round((CH + 4) * scr.devicePixelRatio())))     # Windows считает рабочую область в физических пикселях
        else:
            set_workarea_reserve(0)                                                 # возвращает ИСХОДНУЮ область, а не «весь экран»

        s.set_transparent_input(bool(s.cfg.get('click_through') and s.mode == 'idle'))
        s.place(s.big)

    # ==================== АНИМАЦИЯ 120 FPS, УМНЫЙ ОБХОД ВКЛАДОК И ОТРИСОВКА ====================
    def get_target_screen(s):
        screens = QGuiApplication.screens()
        idx = int(clamp(s.cfg.get('monitor', 0), 0, len(screens) - 1))
        return screens[idx]

    def place(s, big):
        scr = s.get_target_screen()
        s.geo = scr.geometry()
        sc = 1.0                                   # масштаб интерфейса целиком задаёт QT_SCALE_FACTOR (ui_scale), окно не масштабируем отдельно
        w, h = (int((W + 80) * sc), int((H + 80) * sc)) if big else (int(500 * sc), int(92 * sc))
        fit = s.cfg.get('window_fit', 'smart_dodge')
        # В режиме titlebar_snap смещаем остров в свободную зону заголовка справа от вкладок
        auto_ox = int(s.geo.width() * 0.24) if (fit == 'titlebar_snap' and not big and is_foreground_maximized_top()) else 0
        ox = int(s.cfg.get('offset_x', 0)) + auto_ox
        s.setGeometry(s.geo.center().x() - w // 2 + ox, s.geo.top(), w, h)

    def copy_browser_notch_css(s):
        css = (
            "/* Разделитель вкладок под Динамический Остров (userChrome.css для Firefox / Zen) */\n"
            "#TabsToolbar .tabbrowser-tabs {\n"
            "  padding-inline: 8px !important;\n"
            "}\n"
            "#TabsToolbar::before {\n"
            "  content: '';\n"
            "  display: block;\n"
            "  width: 250px;\n"
            "  margin-inline: auto;\n"
            "}\n"
        )
        QGuiApplication.clipboard().setText(css)
        s.pop('CSS выреза скопирован', 'Вставьте в userChrome.css или выберите режим интеграции', (QColor('#34c759'), 'clip'), 4.5)
