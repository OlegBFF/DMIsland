"""Панель «notes»."""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QListWidget, QTextEdit, QVBoxLayout, QWidget,
)
from ui.widgets import TimerRing


class NotesPanel:
    """Часть класса Island: NotesPanel."""

    def pg_notes(s):
        w, h = QWidget(), QHBoxLayout()
        w.setLayout(h)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)

        left = QVBoxLayout()
        left.setSpacing(5)
        ntabs = QHBoxLayout()
        s.note_idx = 0
        for idx, nobj in enumerate(s.cfg['notes']):
            b = s.btn(nobj['title'], lambda _=0, i=idx: s.switch_note(i))
            b.setStyleSheet('padding:4px 10px;font-size:11.5px')
            ntabs.addWidget(b)
        ntabs.addStretch()
        left.addLayout(ntabs)

        s.note = QTextEdit()
        s.note.setHtml(s.cfg['notes'][0].get('html', ''))
        s.nt = QTimer(s, singleShot=True, interval=600)
        s.nt.timeout.connect(s.save_current_note)
        s.note.textChanged.connect(lambda: s.nt.start())
        left.addWidget(s.note, 1)

        fmt = QHBoxLayout()
        for lbl, fn in (('B', lambda: s.fmt_note('b')), ('I', lambda: s.fmt_note('i')),
                        ('S', lambda: s.fmt_note('s')), ('Маркер', lambda: s.fmt_note('hl')),
                        ('Задача', lambda: s.note.insertPlainText('\n☐ '))):
            b = s.btn(lbl, fn)
            b.setStyleSheet('padding:3px 8px;font-size:11px')
            fmt.addWidget(b)
        fmt.addStretch()
        left.addLayout(fmt)

        right = QVBoxLayout()
        right.setSpacing(6)
        tbox = QFrame()
        tbox.setObjectName('bento')
        th = QHBoxLayout(tbox)
        th.setContentsMargins(10, 6, 10, 6)
        s.ring = TimerRing()
        th.addWidget(s.ring)
        tc = QVBoxLayout()
        s.go = s.btn('Старт', s.toggle_timer)
        r_sub = QHBoxLayout()
        r_sub.addWidget(s.btn('+1 мин', lambda: s.set_timer_sec(s.tleft + 60)))
        r_sub.addWidget(s.btn('Сброс', lambda: s.set_timer_sec(25 * 60)))
        tc.addWidget(s.go)
        tc.addLayout(r_sub)
        th.addLayout(tc, 1)
        right.addWidget(tbox)

        s.rem_lw = QListWidget()
        s.rem_lw.setContextMenuPolicy(Qt.CustomContextMenu)
        s.rem_lw.customContextMenuRequested.connect(s.reminder_menu)
        s.rem_lw.itemDoubleClicked.connect(lambda it: s.edit_reminder(it.data(Qt.UserRole)))
        sc = QShortcut(QKeySequence.Delete, s.rem_lw)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(s.delete_selected_reminder)
        right.addWidget(s.rem_lw, 1)
        r_in = QHBoxLayout()
        s.rem_txt = QLineEdit()
        s.rem_txt.setPlaceholderText('в 16:30 позвонить · через 15 мин · по будням в 9:00…')
        s.rem_txt.returnPressed.connect(s.add_reminder)
        r_in.addWidget(s.rem_txt, 1)
        r_in.addWidget(s.btn('+', s.add_reminder))
        b_more = s.btn('⋯', s.add_reminder_dialog)
        b_more.setToolTip('Подробнее: повтор, дни недели, дата')
        r_in.addWidget(b_more)
        right.addLayout(r_in)
        s.refresh_reminders()

        h.addLayout(left, 3)
        h.addLayout(right, 2)
        return w
