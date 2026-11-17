"""Панель «home»."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)
from ui.themes import FD
from ui.widgets import Bar, Slider, VectorBtn


class HomePanel:
    """Часть класса Island: HomePanel."""

    # -------------------- ВКЛАДКА 0: ГЛАВНАЯ --------------------
    def pg_home(s):
        w, g = QWidget(), QGridLayout()
        w.setLayout(g)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        g.setColumnStretch(0, 5)
        g.setColumnStretch(1, 4)

        card = QFrame()
        card.setObjectName('card')
        v = QVBoxLayout(card)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(6)

        top, col = QHBoxLayout(), QVBoxLayout()
        top.setSpacing(12)
        s.cov = QLabel()
        s.cov.setFixedSize(82, 82)
        s.cov.setStyleSheet('background:rgba(0,0,0,75);border-radius:14px;border:0')

        hdr_row = QHBoxLayout()
        s.src_btn = QPushButton('PLAYER ▾')
        s.src_btn.setCursor(Qt.PointingHandCursor)
        s.src_btn.setStyleSheet('background:transparent;border:0;color:rgba(255,255,255,130);font-size:10px;font-weight:700;padding:0')
        s.src_btn.clicked.connect(s.show_players_menu)
        hdr_row.addWidget(s.src_btn)
        hdr_row.addStretch()

        s.ttl = QLabel('Ничего не играет')
        s.ttl.setStyleSheet(f'font-family:{FD};font-size:16px;font-weight:600;border:0;background:transparent')
        s.art = QLabel(' ')
        s.art.setStyleSheet('color:rgba(255,255,255,175);font-size:12px;border:0;background:transparent')
        s.lrc_lab = QLabel('')
        s.lrc_lab.setStyleSheet('color:#ff9f0a;font-size:11px;font-weight:600;border:0;background:transparent')

        col.addLayout(hdr_row)
        col.addWidget(s.ttl)
        col.addWidget(s.art)
        col.addWidget(s.lrc_lab)
        col.addStretch()
        top.addWidget(s.cov)
        top.addLayout(col, 1)
        v.addLayout(top)

        s.bar = Bar()
        v.addWidget(s.bar)

        t_row = QHBoxLayout()
        s.tl_el = QLabel('0:00')
        s.tl_rem = QLabel('-0:00')
        for lb in (s.tl_el, s.tl_rem):
            lb.setStyleSheet('color:rgba(255,255,255,130);font-size:10.5px;border:0;background:transparent')
        t_row.addWidget(s.tl_el)
        t_row.addStretch()
        t_row.addWidget(s.tl_rem)
        v.addLayout(t_row)

        r = QHBoxLayout()
        r.addStretch()
        b_prev = VectorBtn('prev', fn=lambda: s.media.cmd('try_skip_previous_async'), h=36)
        s.pp = VectorBtn('play', badge_col=QColor('#ff4d6d'), fn=lambda: s.media.cmd('try_toggle_play_pause_async'), h=40)
        b_next = VectorBtn('next', fn=lambda: s.media.cmd('try_skip_next_async'), h=36)
        r.addWidget(b_prev)
        r.addSpacing(8)
        r.addWidget(s.pp)
        r.addSpacing(8)
        r.addWidget(b_next)
        r.addStretch()
        v.addLayout(r)
        g.addWidget(card, 0, 0)

        vol_card = QFrame()
        vol_card.setObjectName('bento')
        vol_card.setFixedHeight(38)
        vr = QHBoxLayout(vol_card)
        vr.setContentsMargins(10, 0, 8, 0)
        vr.setSpacing(8)
        s.vol = Slider()
        s.vn = QLabel('50')
        s.vn.setFixedWidth(26)
        s.vn.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        s.vn.setStyleSheet('color:rgba(255,255,255,150);font-size:11.5px;border:0;background:transparent')
        s.dev_btn = QPushButton('Динамики ▾')
        s.dev_btn.setFixedHeight(26)
        s.dev_btn.setStyleSheet('font-size:11px;padding:2px 8px;border-radius:9px')
        s.dev_btn.clicked.connect(s.pick_audio_device)

        s.vol.valueChanged.connect(s.set_volume)
        v0 = s.volume()
        s.vol.setValue(v0)
        s.vn.setText(str(v0))                 # значение уходит в Windows только по действию пользователя

        vr.addWidget(s.vol, 1)
        vr.addWidget(s.vn)
        vr.addWidget(s.dev_btn)
        g.addWidget(vol_card, 1, 0)

        # Правая сетка инструментов с векторными Duotone-иконками
        tl = QGridLayout()
        tl.setSpacing(6)
        tools = [
            ('area', 'Область', QColor('#ff4d6d'), lambda: s.snap('area')),
            ('full', 'Весь экран', QColor('#0a84ff'), s.full_shot),
            ('ocr', 'Текст с экрана', QColor('#5e5ce6'), lambda: s.snap('ocr')),
            ('qr', 'QR-код', QColor('#ff9f0a'), lambda: s.snap('qr')),
            ('pick', 'Пипетка', QColor('#bf5af2'), lambda: s.snap('pick')),
            ('plain', 'Чистый текст', QColor('#34c759'), s.plain),
            ('rec', 'Запись экрана', QColor('#ff453a'), s.toggle_record),
            ('cmd', 'Команда', QColor('#64d2ff'), s.open_command_palette),
        ]
        for idx, (ic_n, name, col, fn) in enumerate(tools):
            b = VectorBtn(ic_n, name, col, fn, h=48)
            tl.addWidget(b, idx // 2, idx % 2)
        g.addLayout(tl, 0, 1, 2, 1)

        dock = QFrame()
        dock.setObjectName('dock')
        dock.setFixedHeight(52)
        s.lr = QHBoxLayout(dock)
        s.lr.setContentsMargins(10, 5, 10, 5)
        s.lr.setSpacing(6)
        g.addWidget(dock, 2, 0, 1, 2)
        s.apps()
        return w
