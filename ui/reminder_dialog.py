"""Диалог создания и редактирования напоминания: одноразовое, ежедневное, по дням недели, ежемесячное, с интервалом."""
from datetime import datetime
from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QTimeEdit, QVBoxLayout, QWidget,
)
from core import schedule
from ui.themes import STYLE, qss


KINDS = [('once', 'Один раз'), ('daily', 'Каждый день'), ('weekly', 'По дням недели'),
         ('monthly', 'Каждый месяц'), ('interval', 'Через равные промежутки')]


class ReminderDialog(QDialog):
    def __init__(s, text='', rule=None, title='Напоминание'):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        s.setWindowTitle(title)
        s.setModal(True)
        th = STYLE['th']
        s.setStyleSheet(f"QDialog{{background:{'#f4f4f9' if STYLE['light'] else th['base2']};}}" + qss(STYLE['acc'], STYLE['light']))
        rule = rule or schedule.once(datetime.now().replace(second=0, microsecond=0))
        now = datetime.now()

        v = QVBoxLayout(s)
        form = QFormLayout()
        form.setSpacing(8)
        s.ed_text = QLineEdit(text)
        s.ed_text.setPlaceholderText('О чём напомнить')
        s.cb_kind = QComboBox()
        for k, n in KINDS:
            s.cb_kind.addItem(n, k)
        s.cb_kind.setCurrentIndex(max(s.cb_kind.findData(rule['type']), 0))
        form.addRow('Текст', s.ed_text)
        form.addRow('Повтор', s.cb_kind)

        s.ed_date = QDateEdit(QDate.currentDate())
        s.ed_date.setCalendarPopup(True)
        s.ed_date.setDisplayFormat('dd.MM.yyyy')
        s.ed_time = QTimeEdit(QTime(now.hour, now.minute))
        s.ed_time.setDisplayFormat('HH:mm')
        s.row_date = s._row('Дата', s.ed_date)
        s.row_time = s._row('Время', s.ed_time)

        days = QWidget()
        dl = QHBoxLayout(days)
        dl.setContentsMargins(0, 0, 0, 0)
        s.day_cb = []
        for i, n in enumerate(schedule.WD_SHORT):
            c = QCheckBox(n)
            s.day_cb.append(c)
            dl.addWidget(c)
        s.row_days = s._row('Дни', days)
        s.sp_day = QSpinBox()
        s.sp_day.setRange(1, 31)
        s.row_mday = s._row('Число месяца', s.sp_day)
        s.sp_min = QSpinBox()
        s.sp_min.setRange(1, 10080)
        s.sp_min.setSuffix(' мин')
        s.row_int = s._row('Каждые', s.sp_min)
        for r in (s.row_date, s.row_time, s.row_days, s.row_mday, s.row_int):
            form.addRow(r[0], r[1])
        v.addLayout(form)
        s.lbl_err = QLabel('')
        s.lbl_err.setStyleSheet('color:#ff453a')
        v.addWidget(s.lbl_err)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText('Сохранить')
        bb.button(QDialogButtonBox.Cancel).setText('Отмена')
        bb.accepted.connect(s._accept)
        bb.rejected.connect(s.reject)
        v.addWidget(bb)

        s._load(rule)
        s.cb_kind.currentIndexChanged.connect(s._sync)
        s._sync()
        s.setMinimumWidth(380)

    @staticmethod
    def _row(label, widget):
        lab = QLabel(label)
        return lab, widget

    def _load(s, r):
        t = r['type']
        if t == 'once':
            at = datetime.strptime(r['at'][:16], '%Y-%m-%dT%H:%M')
            s.ed_date.setDate(QDate(at.year, at.month, at.day))
            s.ed_time.setTime(QTime(at.hour, at.minute))
        elif t == 'interval':
            s.sp_min.setValue(int(r['minutes']))
        else:
            h, m = r['time'].split(':')
            s.ed_time.setTime(QTime(int(h), int(m)))
            for i in (r.get('days') or [0, 1, 2, 3, 4]):
                s.day_cb[i].setChecked(True)
            s.sp_day.setValue(int(r.get('day', 1)))
        if t != 'weekly' and not any(c.isChecked() for c in s.day_cb):
            for c in s.day_cb[:5]:
                c.setChecked(True)
        if t != 'interval':
            s.sp_min.setValue(60)

    def _sync(s):
        k = s.cb_kind.currentData()
        show = {'once': (1, 1, 0, 0, 0), 'daily': (0, 1, 0, 0, 0), 'weekly': (0, 1, 1, 0, 0),
                'monthly': (0, 1, 0, 1, 0), 'interval': (0, 0, 0, 0, 1)}[k]
        for (lab, w), vis in zip((s.row_date, s.row_time, s.row_days, s.row_mday, s.row_int), show):
            lab.setVisible(bool(vis))
            w.setVisible(bool(vis))
        s.adjustSize()

    def build_rule(s) -> dict:
        k, hm = s.cb_kind.currentData(), s.ed_time.time().toString('HH:mm')
        if k == 'once':
            d, t = s.ed_date.date(), s.ed_time.time()
            return schedule.once(datetime(d.year(), d.month(), d.day(), t.hour(), t.minute()))
        if k == 'daily':
            return schedule.daily(hm)
        if k == 'weekly':
            return schedule.weekly(hm, [i for i, c in enumerate(s.day_cb) if c.isChecked()])
        if k == 'monthly':
            return schedule.monthly(hm, s.sp_day.value())
        return schedule.interval(s.sp_min.value(), datetime.now())

    def _accept(s):
        try:
            rule = s.build_rule()
            schedule.validate(rule)
            if schedule.next_occurrence(rule, datetime.now()) is None:
                raise ValueError('Это время уже прошло')
        except ValueError as e:
            s.lbl_err.setText(str(e))
            return
        s.accept()

    def result_value(s):
        return s.ed_text.text().strip() or 'Напоминание', s.build_rule()
