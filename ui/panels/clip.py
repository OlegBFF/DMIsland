"""Панель «clip»: история буфера с поиском и избранным."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget


class ClipPanel:
    """Часть класса Island: ClipPanel."""

    def pg_clip(s):
        w, v = QWidget(), QVBoxLayout()
        w.setLayout(v)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(6)
        s.q = QLineEdit()
        s.q.setPlaceholderText('Поиск по истории (текст, скриншоты, записи)…')
        s.q.textChanged.connect(s.refresh_clip)
        s.clip_fav_only = False
        s.clip_icons = {}
        s.clip_all_btn = s.btn('Все', lambda: s.set_clip_fav_filter(False))
        s.clip_fav_btn = s.btn('★ Избранное', lambda: s.set_clip_fav_filter(True))
        for b in (s.clip_all_btn, s.clip_fav_btn):
            b.setCheckable(True)
        s.clip_all_btn.setChecked(True)
        b_clr = s.btn('Очистить', s.clip_clear)
        b_clr.setToolTip('Удаляет всё, кроме избранного')
        top.addWidget(s.q, 1)
        top.addWidget(s.clip_all_btn)
        top.addWidget(s.clip_fav_btn)
        top.addWidget(b_clr)
        s.lw = QListWidget()
        s.lw.itemClicked.connect(s.pick_clip)
        s.lw.setContextMenuPolicy(Qt.CustomContextMenu)
        s.lw.customContextMenuRequested.connect(s.clip_menu)
        s.clip_count = QLabel('0')
        s.clip_count.hide()
        v.addLayout(top)
        v.addWidget(s.lw, 1)
        s.refresh_clip()
        return w
