"""Полка файлов для перетаскивания (хранится в базе — список переживает перезапуск)."""
import subprocess
from pathlib import Path
from PySide6.QtCore import QFileInfo, QMimeData, QUrl, Qt
from PySide6.QtGui import QBrush, QColor, QDrag
from PySide6.QtWidgets import QFileDialog, QFileIconProvider, QListWidgetItem
from core.security import safe_open_path


class ShelfMixin:
    """Часть класса Island: ShelfMixin."""

    def shelf_add(s, paths):
        n = s.shelves.add(paths)
        s.shelf = s.shelves.paths()
        s.refresh_shelf()
        return n

    def shelf_remove(s, path):
        s.shelves.remove(path)
        s.shelf = s.shelves.paths()
        s.refresh_shelf()

    def shelf_clear(s):
        s.shelves.clear()
        s.shelf = []
        s.refresh_shelf()

    def shelf_remove_missing(s):
        s.shelves.remove_missing()
        s.shelf = s.shelves.paths()
        s.refresh_shelf()

    def add_to_shelf_dialog(s):
        files, _ = QFileDialog.getOpenFileNames(None, 'Добавить файлы на полку')
        if files:
            s.shelf_add(files)

    def refresh_shelf(s):
        if not hasattr(s, 'shelf_lw'):
            return
        s.shelf_lw.clear()
        ip = QFileIconProvider()
        for p in s.shelf:
            exists = Path(p).exists()
            it = QListWidgetItem(ip.icon(QFileInfo(p)), Path(p).name[:18])
            it.setData(Qt.UserRole, p)
            it.setToolTip(p if exists else f'Файл не найден: {p}')
            if not exists:
                it.setForeground(QBrush(QColor(255, 255, 255, 90)))
            s.shelf_lw.addItem(it)
        s.shelf_drag_btn.setText(f'Перетащить все ({len(s.shelf)})')

    def shelf_selected_path(s):
        it = s.shelf_lw.currentItem()
        return it.data(Qt.UserRole) if it else None

    def shelf_menu(s, pos):
        it = s.shelf_lw.itemAt(pos)
        m = s.mk_menu()
        path = it.data(Qt.UserRole) if it else None
        a_open = m.addAction('Открыть') if path else None
        a_dir = m.addAction('Показать в папке') if path else None
        a_rm = m.addAction('Убрать с полки') if path else None
        if path:
            m.addSeparator()
        a_miss = m.addAction('Убрать отсутствующие файлы')
        res = m.exec(s.shelf_lw.mapToGlobal(pos))
        if res is None:
            return
        if a_open and res == a_open:
            safe_open_path(path)
        elif a_dir and res == a_dir and Path(path).exists():
            subprocess.Popen(['explorer', '/select,', str(Path(path).resolve())])
        elif a_rm and res == a_rm:
            s.shelf_remove(path)
        elif res == a_miss:
            s.shelf_remove_missing()

    def drag_all_shelf(s):
        existing = [p for p in s.shelf if Path(p).exists()]
        if not existing:
            return
        d = QDrag(s)
        m = QMimeData()
        m.setUrls([QUrl.fromLocalFile(p) for p in existing])
        d.setMimeData(m)
        d.exec(Qt.CopyAction)
