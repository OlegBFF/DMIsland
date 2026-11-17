"""Панель «shelf»."""
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QVBoxLayout, QWidget
from core.security import safe_open_path


class ShelfPanel:
    """Часть класса Island: ShelfPanel."""

    def pg_shelf(s):
        w, v = QWidget(), QVBoxLayout()
        w.setLayout(v)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        top = QHBoxLayout()
        s.shelf_drag_btn = s.btn('Перетащить все (0)', s.drag_all_shelf)
        b_add = s.btn('+ Добавить файлы', s.add_to_shelf_dialog)
        b_clr = s.btn('Очистить полку', s.shelf_clear)
        top.addWidget(s.shelf_drag_btn)
        top.addWidget(b_add)
        top.addStretch()
        top.addWidget(b_clr)
        s.shelf_lw = QListWidget()
        s.shelf_lw.setViewMode(QListWidget.IconMode)
        s.shelf_lw.setIconSize(QSize(44, 44))
        s.shelf_lw.setGridSize(QSize(110, 82))
        s.shelf_lw.setMovement(QListWidget.Static)
        s.shelf_lw.setContextMenuPolicy(Qt.CustomContextMenu)
        s.shelf_lw.customContextMenuRequested.connect(s.shelf_menu)
        s.shelf_lw.itemDoubleClicked.connect(lambda it: safe_open_path(it.data(Qt.UserRole)))
        sc = QShortcut(QKeySequence.Delete, s.shelf_lw)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(lambda: s.shelf_selected_path() and s.shelf_remove(s.shelf_selected_path()))
        v.addLayout(top)
        v.addWidget(s.shelf_lw, 1)
        s.refresh_shelf()
        return w
