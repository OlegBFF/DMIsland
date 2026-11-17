"""Таймер и напоминания: одноразовые и повторяющиеся, редактирование, откладывание, удаление."""
from datetime import datetime
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QListWidgetItem
from core import schedule
from core.utils import log
from ui.reminder_dialog import ReminderDialog
from ui.themes import STYLE

MISSED_AFTER = 120      # секунд: опоздание больше этого — «Пропущено», а не просто «Напоминание»


class RemindersMixin:
    """Часть класса Island: RemindersMixin."""

    def set_timer_sec(s, secs):
        s.tleft = max(0, secs)
        s.ttotal = max(s.ttotal, s.tleft, 60)
        s.ring.set_time(s.tleft, s.ttotal)

    def toggle_timer(s):
        s.trun = not s.trun
        s.go.setText('Пауза' if s.trun else 'Старт')

    # ---------- создание ----------
    def _rem_warn(s, msg):
        s.pop('Напоминание', msg, (QColor('#ff9f0a'), 'notes'), 4.5)

    def add_reminder(s):
        """Быстрый ввод фразой: «в 16:30 позвонить», «через 15 мин чай», «каждый понедельник в 10:00 отчёт»."""
        raw = s.rem_txt.text().strip()
        if not raw:
            return
        try:
            text, rule = schedule.parse_reminder(raw)
            s.reminders.add(text, rule)
        except ValueError as e:
            s._rem_warn(str(e))
            return
        s.rem_txt.clear()
        s.refresh_reminders()
        s.pop('Напоминание создано', schedule.describe(rule), (QColor('#34c759'), 'notes'), 2.6)

    def add_reminder_dialog(s):
        d = ReminderDialog()
        if d.exec():
            text, rule = d.result_value()
            try:
                s.reminders.add(text, rule)
            except ValueError as e:
                s._rem_warn(str(e))
            s.refresh_reminders()

    def edit_reminder(s, rid):
        r = s.reminders.get(rid)
        if not r:
            return
        d = ReminderDialog(r['text'], r['rule'], 'Изменить напоминание')
        if d.exec():
            text, rule = d.result_value()
            try:
                s.reminders.update(rid, text, rule)
            except ValueError as e:
                s._rem_warn(str(e))
            s.refresh_reminders()

    # ---------- список ----------
    def refresh_reminders(s):
        if not hasattr(s, 'rem_lw'):
            return
        s.rem_lw.clear()
        now = datetime.now()
        for r in s.reminders.all():
            if r['enabled'] and r['due']:
                sub = f"{schedule.describe(r['rule'], now)}  ·  {schedule.format_due(r['due'], now)}"
                it = QListWidgetItem(f"{r['text']}\n{sub}")
            else:
                done = r['rule']['type'] == 'once' and r['fired']
                it = QListWidgetItem(f"{r['text']}\n{'Выполнено' if done else 'Выключено'} · {schedule.describe(r['rule'], now)}")
                it.setForeground(QColor(255, 255, 255, 100))
            it.setData(Qt.UserRole, r['id'])
            s.rem_lw.addItem(it)

    def reminder_menu(s, pos):
        it = s.rem_lw.itemAt(pos)
        if not it:
            return
        rid = it.data(Qt.UserRole)
        r = s.reminders.get(rid)
        if not r:
            return
        m = s.mk_menu()
        a_edit = m.addAction('Изменить…')
        a_snooze = m.addAction('Отложить на 10 минут') if r['enabled'] else None
        a_tog = m.addAction('Выключить' if r['enabled'] else 'Включить')
        m.addSeparator()
        a_del = m.addAction('Удалить')
        res = m.exec(s.rem_lw.mapToGlobal(pos))
        if res is None:
            return
        if res == a_edit:
            s.edit_reminder(rid)
        elif a_snooze and res == a_snooze:
            s.reminders.snooze(rid, 10)
        elif res == a_tog:
            if not s.reminders.set_enabled(rid, not r['enabled']):
                s._rem_warn('Время прошло — измените напоминание')
        elif res == a_del:
            s.reminders.delete(rid)
        s.refresh_reminders()

    def delete_selected_reminder(s):
        it = s.rem_lw.currentItem()
        if it:
            s.reminders.delete(it.data(Qt.UserRole))
            s.refresh_reminders()

    # ---------- тик раз в секунду ----------
    def second(s):
        if s.trun:
            s.tleft -= 1
            s.ring.set_time(s.tleft, s.ttotal)
            if s.tleft <= 0:
                s.trun = False
                s.go.setText('Старт')
                s.set_timer_sec(25 * 60)
                QApplication.beep()
                s.pop('Таймер', 'Время вышло!', (QColor('#ff9f0a'), 'notes'), 8.0)
        s.check_reminders()
        s.check_notif_timers()

    def check_reminders(s):
        try:
            now = datetime.now()
            due = s.reminders.due(now)
            for r in due:
                late = (now - r['due']).total_seconds()
                s.reminders.mark_fired(r['id'], now)
                hm = r['due'].strftime('%H:%M')
                sub = f"Напоминание · {hm}" if late < MISSED_AFTER else f"Пропущено · {schedule.format_due(r['due'], now)}"
                QApplication.beep()
                s.pop(r['text'], sub, (QColor('#ff9f0a'), 'notes'), 15.0)
            if due:
                s.refresh_reminders()
        except Exception as ex:
            log(f"check_reminders: {ex!r}")
