"""Панель «Уведомления»: история с приоритетами, поиском, отложенными и быстрыми действиями."""
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget
from core.notif_rules import PRIORITY_NAMES, snooze_options
from system.util import open_settings
from core.notif_extract import group_by_app, group_summary
from ui.notif_card import NotifGroupHeader, NotifRow

FILTERS = (('all', 'Все'), ('important', 'Важные'), ('system', 'Система'), ('normal', 'Обычные'), ('snoozed', 'Отложенные'))


class NotifsPanel:
    """Часть класса Island: NotifsPanel."""

    def pg_notifs(s):
        w, v = QWidget(), QVBoxLayout()
        w.setLayout(v)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        s.nf_filter, s._nf_sig, s._nf_collapsed = 'all', None, set()

        top = QHBoxLayout()
        top.setSpacing(6)
        s.nf_btns = {}
        for key, label in FILTERS:
            b = s.btn(label, lambda k=key: s.set_notif_filter(k))
            b.setCheckable(True)
            s.nf_btns[key] = b
            top.addWidget(b)
        s.nf_btns['all'].setChecked(True)
        s.nf_grp = s.btn('По приложениям', s.toggle_notif_group)
        s.nf_grp.setCheckable(True)
        s.nf_grp.setChecked(bool(s.cfg.get('notif_group', True)))
        top.addWidget(s.nf_grp)
        s.nf_q = QLineEdit()
        s.nf_q.setPlaceholderText('Поиск')
        s.nf_q.textChanged.connect(lambda _=None: s.refresh_notifs())
        top.addWidget(s.nf_q, 1)
        v.addLayout(top)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        s.nf_hint = QLabel('')
        s.nf_hint.setStyleSheet('color:rgba(255,255,255,140);font-size:11px;border:0;background:transparent')
        s.nf_hint.setWordWrap(True)
        s.nf_perm = s.btn('Разрешить доступ', lambda: open_settings('ms-settings:privacy-notifications'))
        s.nf_dnd = s.btn('Не беспокоить', s.toggle_dnd)
        s.nf_dnd.setCheckable(True)
        row2.addWidget(s.nf_hint, 1)
        row2.addWidget(s.nf_perm)
        row2.addWidget(s.nf_dnd)
        row2.addWidget(s.btn('Прочитано', lambda: (s.notifs.mark_read(), s._after_change())))
        row2.addWidget(s.btn('Очистить', lambda: (s.notifs.clear(keep_unread_important=True), s._after_change())))
        v.addLayout(row2)

        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setStyleSheet('QScrollArea{background:transparent;border:0}')
        body = QWidget()
        body.setStyleSheet('background:transparent')
        s.nf_body = QVBoxLayout(body)
        s.nf_body.setContentsMargins(0, 0, 6, 0)
        s.nf_body.setSpacing(2)
        s.nf_empty = QLabel('Здесь появятся уведомления Windows и события острова')
        s.nf_empty.setAlignment(Qt.AlignCenter)
        s.nf_empty.setStyleSheet('color:rgba(255,255,255,110);font-size:12px;border:0;background:transparent;padding:30px')
        s.nf_body.addWidget(s.nf_empty)
        s.nf_body.addStretch()
        sc.setWidget(body)
        v.addWidget(sc, 1)
        s.refresh_notifs()
        return w

    def set_notif_filter(s, key):
        s.nf_filter = key
        for k, b in s.nf_btns.items():
            b.setChecked(k == key)
        s._nf_sig = None
        s.refresh_notifs()

    def toggle_notif_group(s):
        s.set_cfg('notif_group', not s.cfg.get('notif_group', True))
        s.nf_grp.setChecked(bool(s.cfg.get('notif_group', True)))
        s._nf_sig = None
        s.refresh_notifs()

    def _toggle_group(s, key):
        s._nf_collapsed ^= {key}
        s._nf_sig = None
        s.refresh_notifs()

    def _group_read(s, key):
        s.notifs.mark_read_app(key)
        s._after_change()

    def _group_clear(s, key):
        s.notifs.delete_app(key)
        s._after_change()

    def _make_row(s, n):
        row = NotifRow(s.nicons)
        row.set_data(n)
        row.clicked.connect(s.notif_open)
        row.snoozeClicked.connect(s.notif_snooze_menu)
        row.deleteClicked.connect(lambda n: (s.notifs.delete(n['id']), s._after_change()))
        row.contextRequested.connect(s.notif_row_menu)
        return row

    def refresh_notifs(s):
        if not hasattr(s, 'nf_body'):
            return
        f = s.nf_filter
        items = s.notifs.items(priority=f if f in PRIORITY_NAMES else None, query=s.nf_q.text(),
                               snoozed_only=(f == 'snoozed'), limit=150)
        denied = s.nstatus == 'denied'
        s.nf_perm.setVisible(denied)
        s.nf_hint.setText('Windows не разрешает читать уведомления: Параметры → Конфиденциальность → Уведомления.' if denied else
                          ('Режим «Не беспокоить»: показываются только важные' if s.cfg.get('notif_dnd') else ''))
        s.nf_hint.setVisible(bool(s.nf_hint.text()))
        s.nf_dnd.setChecked(bool(s.cfg.get('notif_dnd')))
        grouped = bool(s.cfg.get('notif_group', True)) and f != 'snoozed' and not s.nf_q.text().strip()
        sig = [grouped, tuple(sorted(s._nf_collapsed))] + [(n['id'], n['read'], n['count'], n.get('snooze_until')) for n in items]
        if sig == s._nf_sig:
            return
        s._nf_sig = sig
        for i in reversed(range(s.nf_body.count() - 1)):
            w = s.nf_body.itemAt(i).widget()
            if w is not None and w is not s.nf_empty:
                s.nf_body.removeWidget(w)
                w.deleteLater()
        if grouped:
            for key, app, its in group_by_app(items):
                hd = NotifGroupHeader(s.nicons)
                hd.set_data(key, app, its, group_summary(its), key in s._nf_collapsed)
                hd.toggled.connect(s._toggle_group)
                hd.readClicked.connect(s._group_read)
                hd.clearClicked.connect(s._group_clear)
                s.nf_body.insertWidget(s.nf_body.count() - 1, hd)
                if key not in s._nf_collapsed:
                    for n in its:
                        s.nf_body.insertWidget(s.nf_body.count() - 1, s._make_row(n))
        else:
            for n in items:
                s.nf_body.insertWidget(s.nf_body.count() - 1, s._make_row(n))
        s.nf_empty.setVisible(not items)

    def notif_row_menu(s, n, pos):
        m = s.mk_menu()
        a_reply = m.addAction('Ответить…') if s.replies.find(n) else None
        sub = m.addMenu('Отложить')
        for label, when in snooze_options(datetime.now()):
            sub.addAction(label).triggered.connect(lambda _=False, w=when: (s.notifs.snooze(n['id'], w.timestamp()), s._after_change()))
        a_open = m.addAction('Открыть приложение')
        a_read = m.addAction('Отметить прочитанным')
        m.addSeparator()
        app = (n.get('app') or '').strip()
        a_imp = m.addAction(f'Всегда важное: {app}') if app and n['source'] == 'windows' else None
        a_mute = m.addAction(f'Не показывать: {app}') if app and n['source'] == 'windows' else None
        a_del = m.addAction('Удалить')
        res = m.exec(pos.toPoint())
        if res is None:
            return
        if a_reply and res == a_reply:
            s.notif_reply_dialog(n)
        elif res == a_open:
            s.notif_open(n)
        elif res == a_read:
            s.notifs.mark_read(n['id'])
            s._after_change()
        elif a_imp and res == a_imp:
            s.add_app_rule('notif_important_apps', app)
        elif a_mute and res == a_mute:
            s.add_app_rule('notif_muted_apps', app)
        elif res == a_del:
            s.notifs.delete(n['id'])
            s._after_change()
