"""Тесты вспомогательной логики уведомлений: разбор текстов, diff, форматирование времени, провайдеры ответа."""
import time
import unittest
from datetime import datetime

from core.notif_rules import format_time
from modules.notify_reply import OpenAndCopyProvider, ReplyProvider, ReplyRegistry


class FakeWin(ReplyProvider):
    name = 'fake'

    def can_reply(self, n):
        return n.get('app') == 'Fake'

    def send(self, n, text):
        return True, f"sent:{text}"


class Misc(unittest.TestCase):
    def test_diff_and_split(self):
        from tests.qt_stub import install
        install()
        from modules.winnotify import diff_new, split_texts
        new, seen = diff_new({1, 2}, [2, 3, 4])
        self.assertEqual((new, seen), ([3, 4], {2, 3, 4}))
        self.assertEqual(diff_new(seen, [])[1], set())                    # исчезнувшие забываются — множество не растёт
        self.assertEqual(split_texts(['Аня', 'Привет', 'как дела?']), ('Аня', 'Привет\nкак дела?'))
        self.assertEqual(split_texts(['Только заголовок']), ('Только заголовок', ''))
        self.assertEqual(split_texts([]), ('', ''))

    def test_format_time(self):
        now = datetime(2026, 11, 14, 15, 0).timestamp()
        f = lambda dt: format_time(datetime(*dt).timestamp(), now)
        self.assertEqual(f((2026, 11, 14, 14, 59, 50)), 'сейчас')
        self.assertEqual(f((2026, 11, 14, 14, 40)), '20 мин назад')
        self.assertEqual(f((2026, 11, 14, 9, 5)), 'сегодня 09:05')
        self.assertEqual(f((2026, 11, 13, 21, 30)), 'вчера 21:30')
        self.assertEqual(f((2026, 11, 11, 8, 0)), 'ср 08:00')
        self.assertEqual(f((2026, 11, 2, 8, 0)), '2 ноя')

    def test_open_and_copy_provider(self):
        copied = []
        pr = OpenAndCopyProvider(copied.append)
        self.assertTrue(pr.can_reply({'source': 'windows', 'app_id': 'Telegram.Desktop'}))
        self.assertFalse(pr.can_reply({'source': 'island', 'app_id': 'x'}))
        self.assertFalse(pr.can_reply({'source': 'windows', 'app_id': ''}))
        ok, msg = pr.send({'source': 'windows', 'app_id': 'bad;&calc'}, 'привет')      # опасный AUMID не запускается
        self.assertTrue(ok)
        self.assertEqual(copied, ['привет'])
        self.assertIn('не удалось', msg)

    def test_registry_prefers_registered_provider(self):
        reg = ReplyRegistry([OpenAndCopyProvider(lambda t: None)])
        n = {'app': 'Fake', 'source': 'windows', 'app_id': 'x'}
        self.assertEqual(reg.find(n).name, 'open-and-copy')
        reg.register(FakeWin())
        self.assertEqual(reg.reply(n, ' hi '), (True, 'sent:hi'))
        self.assertEqual(ReplyRegistry().reply(n, 'x')[0], False)


if __name__ == '__main__':
    unittest.main()


class Snooze(unittest.TestCase):
    def test_options(self):
        from core.notif_rules import snooze_options
        morning = snooze_options(datetime(2026, 11, 14, 10, 0))
        self.assertEqual([o[0] for o in morning][-2:], ['Сегодня вечером (18:00)', 'Завтра утром (9:00)'])
        self.assertEqual(morning[0][1], datetime(2026, 11, 14, 10, 5))
        self.assertEqual(morning[-1][1], datetime(2026, 11, 15, 9, 0))
        late = snooze_options(datetime(2026, 11, 14, 17, 0))            # до 18:00 меньше трёх часов — «вечером» не предлагаем
        self.assertNotIn('Сегодня вечером (18:00)', [o[0] for o in late])
        self.assertTrue(all(o[1] > datetime(2026, 11, 14, 17, 0) for o in late))
