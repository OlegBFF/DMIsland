"""Ярлыки приложений и группы."""
from pathlib import Path
from PySide6.QtCore import QFileInfo, QPoint, QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QFileDialog, QFileIconProvider, QInputDialog, QMenu
from core.config import save_cfg
from core.security import safe_open_path
from ui.widgets import AppBtn


class AppsMixin:
    """Часть класса Island: AppsMixin."""

    # ==================== ЛАУНЧЕР, ПОЛКА И БУФЕР ====================
    def apps(s):
        while s.lr.count():
            it = s.lr.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        ip = QFileIconProvider()
        for idx, item in enumerate(s.cfg['apps']):
            kind = item.get('type', 'app')
            b = AppBtn(idx, kind)
            b.droppedOn.connect(s.merge_apps_into_group)
            if kind == 'group':
                b.setToolTip(item.get('name', 'Группа'))
                b.clicked.connect(lambda _=0, i=idx, btn=b: s.open_app_group(i, btn))
            elif kind == 'url':
                b.setToolTip(item.get('path', ''))
                b.clicked.connect(lambda _=0, p=item['path']: safe_open_path(p))
            else:
                p = item.get('path', '')
                b.setIcon(ip.icon(QFileInfo(p)))
                b.setIconSize(QSize(26, 26))
                b.setToolTip(item.get('name', Path(p).stem))
                b.clicked.connect(lambda _=0, p=p: safe_open_path(p))
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, i=idx, btn=b: s.app_context_menu(i, btn.mapToGlobal(pos)))
            s.lr.addWidget(b)

        add_b = s.btn('+', s.add_app_menu)
        add_b.setFixedSize(40, 40)
        add_b.setStyleSheet('border:1px dashed rgba(255,255,255,55);border-radius:12px;font-size:16px')
        s.lr.addWidget(add_b)
        s.lr.addStretch()

    def merge_apps_into_group(s, src, dst):
        a = s.cfg['apps'][src]
        b = s.cfg['apps'][dst]
        if b.get('type') == 'group':
            b['items'].append(a)
        else:
            s.cfg['apps'][dst] = {'type': 'group', 'name': 'Группа', 'items': [b, a]}
        s.cfg['apps'].pop(src)
        save_cfg(s.cfg)
        s.apps()

    def open_app_group(s, idx, btn):
        grp = s.cfg['apps'][idx]
        m = QMenu(s)
        m.setStyleSheet("QMenu{background:#1c1c21;color:#fff;border-radius:12px;padding:6px}QMenu::item:selected{background:rgba(255,255,255,30)}")
        for sub in grp.get('items', []):
            act = m.addAction(sub.get('name') or Path(sub.get('path', '')).stem)
            act.triggered.connect(lambda _=0, p=sub.get('path', ''): safe_open_path(p))
        m.exec(btn.mapToGlobal(QPoint(0, -m.sizeHint().height())))

    def add_app_menu(s):
        m = QMenu(s)
        a_file = m.addAction('Программа или файл…')
        a_url = m.addAction('Безопасная ссылка (https:// или steam://)…')
        res = m.exec(QCursor.pos())
        if res == a_file:
            f, _ = QFileDialog.getOpenFileName(None, 'Программа или файл для лаунчера')
            if f:
                s.cfg['apps'].append({'type': 'app', 'name': Path(f).stem, 'path': f})
                save_cfg(s.cfg)
                s.apps()
        elif res == a_url:
            u, ok = QInputDialog.getText(None, 'Добавить ссылку', 'URL (https://... или steam://run/<id>):')
            if ok and u.strip():
                s.cfg['apps'].append({'type': 'url', 'name': u.strip()[:24], 'path': u.strip()})
                save_cfg(s.cfg)
                s.apps()

    def app_context_menu(s, idx, gpos):
        m = QMenu(s)
        a_edit = m.addAction('Изменить путь / ссылку')
        a_del = m.addAction('Убрать из лаунчера')
        res = m.exec(gpos)
        if res == a_del:
            s.cfg['apps'].pop(idx)
            save_cfg(s.cfg)
            s.apps()
        elif res == a_edit:
            cur = s.cfg['apps'][idx].get('path', '')
            u, ok = QInputDialog.getText(None, 'Изменить ярлык', 'Новый путь или URL:', text=cur)
            if ok and u.strip():
                s.cfg['apps'][idx]['path'] = u.strip()
                save_cfg(s.cfg)
                s.apps()
