"""Фокус клавиатуры по требованию.

Остров по умолчанию не активируется (клики не крадут фокус у вашей работы). Но тогда поля ввода — поиск, чат, быстрый
ответ — не получали бы клавиатуру. Теперь при клике в поле ввода окно на время набора активируется, а когда фокус
уходит из поля — возвращает активное окно прежнему владельцу.
"""
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit
from core.win32 import force_foreground, restore_foreground, set_no_activate

INPUTS = (QLineEdit, QTextEdit, QPlainTextEdit)


class FocusMixin:
    """Часть класса Island: FocusMixin."""

    def init_focus(s):
        s._typing, s._prev_fg = False, 0
        app = QApplication.instance()
        app.installEventFilter(s)
        app.focusChanged.connect(s._on_focus_changed)

    def _is_island_input(s, w) -> bool:
        return isinstance(w, INPUTS) and w is not None and s.isAncestorOf(w)

    def eventFilter(s, obj, ev):
        if ev.type() == QEvent.MouseButtonPress and s._is_island_input(obj):
            s.set_typing(True)
            QTimer.singleShot(0, obj.setFocus)
        return False

    def set_typing(s, on: bool):
        if on == s._typing:
            return
        s._typing = on
        hwnd = int(s.winId())
        if on:
            set_no_activate(hwnd, False)
            s._prev_fg = force_foreground(hwnd)
        else:
            set_no_activate(hwnd, True)
            if s._prev_fg and s._prev_fg != hwnd:
                restore_foreground(s._prev_fg)
            s._prev_fg = 0

    def _on_focus_changed(s, old, new):
        if s._typing and not s._is_island_input(new):
            QTimer.singleShot(250, s._end_typing_if_idle)

    def _end_typing_if_idle(s):
        if s._typing and not s._is_island_input(QApplication.focusWidget()):
            s.set_typing(False)
