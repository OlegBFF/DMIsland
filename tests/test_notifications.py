"""Тесты центра уведомлений: приоритеты, политика показа, тихие часы, хранилище."""
import unittest
from datetime import datetime

from core.db import Database
from core.notif_rules import (classify, in_quiet_hours, is_muted, policy, resolve_ui_scale, split_list)
from core.stores import NotificationStore


class Classify(unittest.TestCase):
    def test_messengers_are_important(self):
        self.assertEqual(classify('Telegram', 'Telegram.Desktop', 'Аня', 'Привет'), 'important')
        self.assertEqual(classify('WhatsApp', '5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App', 'Мама', 'Позвони'), 'important')

    def test_system_events(self):
        self.assertEqual(classify('Безопасность Windows', 'Windows.SystemToast.SecurityAndMaintenance', 'Угроза', 'x'), 'system')
        self.assertEqual(classify('Параметры', 'windows.immersivecontrolpanel_cw5n1h2txyewy!microsoft.windows.immersivecontrolpanel', 'Обновление', ''), 'system')
        self.assertEqual(classify('Island', '', 'USB подключён', 'E:', source='island'), 'system')

    def test_normal_and_keywords(self):
        self.assertEqual(classify('Chrome', 'Chrome', 'Новости', 'Курс валют'), 'normal')
        self.assertEqual(classify('Gmail', 'x', 'Счёт', 'Код подтверждения: 123456'), 'important')
        self.assertEqual(classify('Chrome', 'x', 'Релиз', 'Дедлайн сегодня', keywords='дедлайн'), 'important')
        self.assertEqual(classify('Steam', 'steam', 'Скидки', '', important_apps='steam'), 'important')

    def test_muted_apps(self):
        self.assertTrue(is_muted('Spotify', 'spotify.exe', 'spotify; reddit'))
        self.assertFalse(is_muted('Telegram', 'tg', 'spotify'))
        self.assertEqual(split_list(' A ,b;; C '), ['a', 'b', 'c'])


class Policy(unittest.TestCase):
    NOON = datetime(2026, 11, 14, 12, 0)
    NIGHT = datetime(2026, 11, 14, 23, 30)
    EARLY = datetime(2026, 11, 15, 6, 0)

    def test_quiet_hours_cross_midnight(self):
        self.assertTrue(in_quiet_hours(self.NIGHT, '23:00', '08:00'))
        self.assertTrue(in_quiet_hours(self.EARLY, '23:00', '08:00'))
        self.assertFalse(in_quiet_hours(self.NOON, '23:00', '08:00'))
        self.assertFalse(in_quiet_hours(self.NIGHT, '', ''))
        self.assertTrue(in_quiet_hours(self.NOON, '09:00', '18:00'))

    def test_defaults(self):
        self.assertEqual(policy('important', {}, self.NOON)['show'], 'card')
        self.assertEqual(policy('important', {}, self.NOON)['secs'], 15.0)
        self.assertEqual(policy('normal', {}, self.NOON)['show'], 'toast')
        self.assertEqual(policy('system', {'notif_system': 'card'}, self.NOON)['show'], 'card')

    def test_dnd_lets_important_through(self):
        cfg = {'notif_dnd': True}
        self.assertEqual(policy('important', cfg, self.NOON)['show'], 'card')
        self.assertEqual(policy('normal', cfg, self.NOON)['reason'], 'dnd')
        self.assertEqual(policy('important', dict(cfg, notif_dnd_important=False), self.NOON)['show'], 'silent')

    def test_quiet_hours_apply(self):
        cfg = {'notif_quiet_from': '23:00', 'notif_quiet_to': '08:00'}
        self.assertEqual(policy('normal', cfg, self.NIGHT)['show'], 'silent')
        self.assertEqual(policy('important', cfg, self.NIGHT)['show'], 'card')
        self.assertEqual(policy('normal', cfg, self.NOON)['show'], 'toast')

    def test_fullscreen_and_recording_are_silent(self):
        self.assertEqual(policy('important', {}, self.NOON, fullscreen=True)['reason'], 'fullscreen')
        self.assertEqual(policy('normal', {}, self.NOON, recording=True)['show'], 'silent')
        self.assertEqual(policy('important', {}, self.NOON, recording=True)['show'], 'card')

    def test_disabled(self):
        self.assertEqual(policy('important', {'notif_enabled': False}, self.NOON)['show'], 'silent')

    def test_ui_scale(self):
        self.assertEqual(resolve_ui_scale('auto', 1366), 0.9)
        self.assertEqual(resolve_ui_scale('auto', 1920), 1.0)
        self.assertEqual(resolve_ui_scale('auto', 2560), 1.2)
        self.assertEqual(resolve_ui_scale('auto', 3840), 1.4)
        self.assertEqual(resolve_ui_scale('auto', None), 1.0)
        self.assertEqual(resolve_ui_scale('1.15', 1920), 1.15)
        self.assertEqual(resolve_ui_scale('мусор', 1920), 1.0)
        self.assertEqual(resolve_ui_scale('9', 1920), 2.0)


class Store(unittest.TestCase):
    def setUp(self):
        self.st = NotificationStore(Database(':memory:'))

    def add(self, title='Аня', body='Привет', prio='important', now=1000.0, win_id=None, app='Telegram'):
        return self.st.add('windows', 'tg', app, title, body, prio, now, win_id)

    def test_dedupe_by_win_id_and_repeat_text(self):
        a, new = self.add(win_id=7)
        self.assertTrue(new)
        b, new2 = self.add(win_id=7, now=1500)
        self.assertEqual((a, new2), (b, False))
        c, new3 = self.add(title='Боб', now=1500)
        self.assertTrue(new3)
        d, new4 = self.add(title='Боб', now=1505)              # тот же текст через 5 с — счётчик, а не новая запись
        self.assertEqual((c, new4), (d, False))
        self.assertEqual(self.st.get(c)['count'], 2)
        e, new5 = self.add(title='Боб', now=1600)              # а через минуту — уже новое
        self.assertTrue(new5)

    def test_filters_search_and_counts(self):
        self.add(prio='important', now=1)
        self.add(title='Обновление', body='Доступно', prio='system', now=2, app='Параметры')
        self.add(title='Новости', body='Курс', prio='normal', now=3, app='Chrome')
        self.assertEqual([r['title'] for r in self.st.items()], ['Новости', 'Обновление', 'Аня'])
        self.assertEqual([r['title'] for r in self.st.items(priority='system')], ['Обновление'])
        self.assertEqual([r['title'] for r in self.st.items(query='ПРИВЕТ')], ['Аня'])       # регистр кириллицы
        self.assertEqual(self.st.unread_counts(now=10), {'important': 1, 'system': 1, 'normal': 1})
        self.st.mark_read(priority='normal')
        self.assertEqual(self.st.unread_counts(now=10)['normal'], 0)
        self.st.mark_read()
        self.assertEqual(sum(self.st.unread_counts(now=10).values()), 0)

    def test_snooze_returns_unread_when_due(self):
        nid, _ = self.add(now=100)
        self.st.snooze(nid, until=700)
        self.assertEqual(self.st.unread_counts(now=200)['important'], 0)
        self.assertEqual([r['id'] for r in self.st.items(snoozed_only=True, now=200)], [nid])
        self.assertEqual(self.st.due_snoozed(now=600), [])
        due = self.st.due_snoozed(now=701)
        self.assertEqual([r['id'] for r in due], [nid])
        self.assertEqual(self.st.unread_counts(now=701)['important'], 1)
        self.assertEqual(self.st.due_snoozed(now=702), [])         # второй раз не повторяется

    def test_clear_delete_prune(self):
        a, _ = self.add(title='a', prio='important', now=1000)
        self.add(title='b', prio='normal', now=1001)
        self.st.clear(keep_unread_important=True)
        self.assertEqual([r['title'] for r in self.st.items()], ['a'])
        self.st.add('windows', 'x', 'X', 'old', '', 'normal', 1)
        self.assertGreaterEqual(self.st.prune(keep_days=1, now=1 + 3 * 86400), 1)
        self.st.delete(a)
        self.assertEqual(self.st.items(), [])


if __name__ == '__main__':
    unittest.main()
