"""Выполнение команд ассистента (громкость, музыка, заметки, сайты, приложения…). Разбор — в core/commands.py."""
import ctypes
import html
import os
from datetime import datetime
from PySide6.QtGui import QGuiApplication, QTextCursor, QTextDocument
from core import schedule
from core.commands import TABS, TAB_TITLES
from core.config import save_cfg
from core.security import safe_open_path
from core.utils import log
from modules.app_finder import find_launcher_app, find_shortcut
from ui.themes import STYLE

MEDIA_CMDS = {'pause': 'try_pause_async', 'play': 'try_play_async', 'next': 'try_skip_next_async', 'prev': 'try_skip_previous_async'}
WEEKDAYS = ('понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье')
MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')


class AssistantCmdMixin:
    """Часть класса Island: исполнение команд. exec_command → (успех, текст результата)."""

    def exec_command(s, cmd):
        try:
            fn = getattr(s, f'_cmd_{cmd.action}', None)
            if fn is None:
                return False, 'Эта команда пока не поддерживается'
            res = fn(cmd.args)
            if isinstance(res, tuple):
                return res
            return True, cmd.label
        except Exception as ex:
            log(f'exec_command {cmd.action}: {ex!r}')
            return False, f'Не получилось: {str(ex)[:80] or type(ex).__name__}'

    # ---------- звук и экран ----------
    def _cmd_volume(s, a):
        m = a['mode']
        if m == 'set':
            s.hub.set_volume(a['value'])
        elif m == 'delta':
            s.hub.step_volume(a['value'])
        elif m == 'mute':
            s.hub.set_mute(True)
        else:
            s.hub.set_mute(False)
        s.hub.refresh()

    def _cmd_brightness(s, a):
        if a['mode'] == 'set':
            s.hub.set_brightness(a['value'])
        else:
            s.hub.step_brightness(a['value'])

    def _cmd_media(s, a):
        if not s.media.cur:
            return False, 'Сейчас нет активного плеера'
        s.media.cmd(MEDIA_CMDS[a['cmd']])

    def _cmd_media_info(s, a):
        if not s.mtitle:
            return True, 'Сейчас ничего не играет'
        return True, f"{s.mtitle} — {s.martist}" if s.martist else s.mtitle

    # ---------- таймер, напоминания, заметки ----------
    def _cmd_timer(s, a):
        if a.get('secs'):
            s.ttotal = a['secs']
            s.set_timer_sec(a['secs'])
        s.trun = True
        s.go.setText('Пауза')

    def _cmd_timer_stop(s, a):
        s.trun = False
        s.ttotal = 25 * 60
        s.set_timer_sec(25 * 60)
        s.go.setText('Старт')

    def _cmd_reminder(s, a):
        if not a.get('raw'):
            return False, 'Что и когда напомнить? Например: «напомни через 15 минут позвонить»'
        try:
            text, rule = schedule.parse_reminder(a['raw'])
            s.reminders.add(text, rule)
        except ValueError as e:
            return False, str(e)
        s.refresh_reminders()
        return True, f"Напомню: {text} · {schedule.describe(rule)}"

    def add_quick_note(s, text: str):
        """Дописывает строку в первую заметку (даже если открыта другая) с отметкой времени."""
        s.save_current_note()
        n = s.cfg['notes'][0]
        doc = QTextDocument()
        doc.setHtml(n.get('html', ''))
        cur = QTextCursor(doc)
        cur.movePosition(QTextCursor.End)
        stamp = datetime.now().strftime('%d.%m %H:%M')
        cur.insertHtml(f"<p>• {html.escape(text)} <span style='color:#8e8e93'>({stamp})</span></p>")
        n['html'] = doc.toHtml()
        save_cfg(s.cfg)
        if s.note_idx == 0:
            s.note.blockSignals(True)
            s.note.setHtml(n['html'])
            s.note.blockSignals(False)

    def _cmd_note(s, a):
        if not a.get('text'):
            s.go_tab('notes')
            return True, 'Открываю заметки — что записать?'
        s.add_quick_note(a['text'])
        return True, f"Записал в «{s.cfg['notes'][0]['title']}»: {a['text'][:50]}"

    # ---------- сайты и программы ----------
    def _cmd_open_url(s, a):
        return (True, '') if safe_open_path(a['url']) else (False, 'Не удалось открыть ссылку')

    def _cmd_open_app(s, a):
        name = a['name']
        if a.get('builtin'):
            os.startfile(a['target'])
            return True, f'Запускаю {name}'
        path = find_launcher_app(name, s.cfg.get('apps'))
        if path and safe_open_path(path):
            return True, f'Запускаю {name}'
        lnk = find_shortcut(name)
        if lnk:
            os.startfile(lnk)
            return True, f'Запускаю {os.path.splitext(os.path.basename(lnk))[0]}'
        return False, f'Не нашёл приложение «{name}»'

    # ---------- сам остров ----------
    def go_tab(s, key):
        i = TABS[key]
        s.tabs.idx = i
        s.switch(i)
        s.mode, s.leave = 'open', 0
        s.tabs.update()

    def _cmd_tab(s, a):
        s.go_tab(a['tab'])
        return True, f"Открываю: {TAB_TITLES[a['tab']]}"

    def _cmd_island_close(s, a):
        s.close_island()

    def _cmd_island_pin(s, a):
        s.tabs.pinned = bool(a['on'])
        if a['on']:
            s.mode, s.leave = 'open', 0
        s.tabs.update()

    def _cmd_new_chat(s, a):
        s.new_chat()

    def _cmd_dnd(s, a):
        s.set_cfg('notif_dnd', bool(a['on']))
        s.refresh_notifs()

    def _cmd_notif_read_all(s, a):
        s.notifs.mark_read()
        s._after_change()

    def _cmd_notif_clear(s, a):
        s.notifs.clear(keep_unread_important=True)
        s._after_change()

    def _cmd_theme(s, a):
        m = a['mode']
        s.set_cfg('theme', 'light' if (m == 'light' or (m == 'toggle' and not STYLE['light'])) else 'obsidian')

    def _cmd_ocr(s, a):
        s.snap('ocr')

    def _cmd_shot_full(s, a):
        s.full_shot()

    def _cmd_shot_area(s, a):
        s.snap('area')

    def _cmd_lock(s, a):
        ctypes.windll.user32.LockWorkStation()

    def _cmd_time(s, a):
        return True, datetime.now().strftime('Сейчас %H:%M')

    def _cmd_date(s, a):
        d = datetime.now()
        return True, f"Сегодня {WEEKDAYS[d.weekday()]}, {d.day} {MONTHS[d.month - 1]} {d.year}"

    def _cmd_dictate(s, a):
        QGuiApplication.clipboard().setText(a['text'])
        return True, 'Текст в буфере обмена'
