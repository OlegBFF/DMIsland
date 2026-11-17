"""Тесты расписаний, разбора фраз и детектора секретов."""
import unittest
from datetime import datetime

from core import schedule as sc
from core.secrets_detect import classify, iban_ok, luhn_ok

NOW = datetime(2026, 11, 14, 12, 0, 0)     # суббота


class NextOccurrence(unittest.TestCase):
    def test_once(self):
        r = sc.once(datetime(2026, 11, 14, 13, 0))
        self.assertEqual(sc.next_occurrence(r, NOW), datetime(2026, 11, 14, 13, 0))
        self.assertIsNone(sc.next_occurrence(r, datetime(2026, 11, 14, 13, 0)))

    def test_daily_rolls_over(self):
        self.assertEqual(sc.next_occurrence(sc.daily('11:00'), NOW), datetime(2026, 11, 15, 11, 0))
        self.assertEqual(sc.next_occurrence(sc.daily('12:00'), NOW), datetime(2026, 11, 15, 12, 0))   # строго позже
        self.assertEqual(sc.next_occurrence(sc.daily('12:30'), NOW), datetime(2026, 11, 14, 12, 30))

    def test_weekly(self):
        r = sc.weekly('09:00', [0, 2])                            # пн, ср
        self.assertEqual(sc.next_occurrence(r, NOW), datetime(2026, 11, 16, 9, 0))
        self.assertEqual(sc.next_occurrence(r, datetime(2026, 11, 16, 9, 0)), datetime(2026, 11, 18, 9, 0))

    def test_monthly_clamps_to_month_end(self):
        r = sc.monthly('10:00', 31)
        self.assertEqual(sc.next_occurrence(r, datetime(2026, 2, 1)), datetime(2026, 2, 28, 10, 0))
        self.assertEqual(sc.next_occurrence(r, datetime(2026, 12, 31, 10, 0)), datetime(2027, 1, 31, 10, 0))

    def test_interval(self):
        r = sc.interval(90, NOW)
        self.assertEqual(sc.next_occurrence(r, NOW), datetime(2026, 11, 14, 13, 30))
        self.assertEqual(sc.next_occurrence(r, datetime(2026, 11, 14, 13, 30)), datetime(2026, 11, 14, 15, 0))

    def test_validate(self):
        for bad in ({'type': 'x'}, sc.weekly('09:00', []), sc.monthly('09:00', 40)):
            with self.assertRaises(ValueError):
                sc.validate(bad)
        sc.validate(sc.daily('09:00'))


class Parse(unittest.TestCase):
    def p(self, s):
        return sc.parse_reminder(s, NOW)

    def test_time_only_means_next_occurrence_once(self):
        t, r = self.p('Позвонить маме в 16:30')
        self.assertEqual((t, r['type'], r['at']), ('Позвонить маме', 'once', '2026-11-14T16:30:00'))
        _, r = self.p('зарядка в 8:00')
        self.assertEqual(r['at'], '2026-11-15T08:00:00')           # на сегодня 8:00 уже прошло → завтра

    def test_relative(self):
        t, r = self.p('напомни мне выпить воды через 15 минут')
        self.assertEqual((t, r['at']), ('выпить воды', '2026-11-14T12:15:00'))
        self.assertEqual(self.p('через 2 часа духовка')[1]['at'], '2026-11-14T14:00:00')
        self.assertEqual(self.p('через полчаса чай')[1]['at'], '2026-11-14T12:30:00')

    def test_recurring(self):
        self.assertEqual(self.p('каждый день в 8:00 зарядка')[1], sc.daily('08:00'))
        self.assertEqual(self.p('по будням в 9:30 планёрка')[1], sc.weekly('09:30', [0, 1, 2, 3, 4]))
        self.assertEqual(self.p('по выходным в 11:00 спорт')[1], sc.weekly('11:00', [5, 6]))
        t, r = self.p('каждый понедельник в 10:00 отчёт')
        self.assertEqual((t, r), ('отчёт', sc.weekly('10:00', [0])))
        self.assertEqual(self.p('каждое 15 число в 10:00 платёж')[1], sc.monthly('10:00', 15))
        r = self.p('каждые 90 минут разминка')[1]
        self.assertEqual((r['type'], r['minutes']), ('interval', 90))

    def test_dates_and_weekdays(self):
        self.assertEqual(self.p('завтра в 9 утра врач')[1]['at'], '2026-11-15T09:00:00')
        self.assertEqual(self.p('в 7 вечера ужин')[1]['at'], '2026-11-14T19:00:00')
        self.assertEqual(self.p('в пятницу в 18:00 кино')[1]['at'], '2026-11-20T18:00:00')
        self.assertEqual(self.p('20.11 в 14:00 встреча')[1]['at'], '2026-11-20T14:00:00')
        self.assertEqual(self.p('2026-12-01 10:00 сдать')[1]['at'], '2026-12-01T10:00:00')
        self.assertEqual(self.p('10.01 в 10:00 ДР')[1]['at'], '2027-01-10T10:00:00')      # прошедшая дата → следующий год

    def test_errors_are_human_readable(self):
        for bad in ('купить хлеб', 'сегодня в 11:00 уже было', '14.11 в 9:00 прошло', 'в 25:00 что-то', 'каждый день зарядка'):
            with self.assertRaises(ValueError, msg=bad):
                self.p(bad)

    def test_describe(self):
        self.assertEqual(sc.describe(sc.weekly('09:30', [0, 1, 2, 3, 4]), NOW), 'По будням · 09:30')
        self.assertEqual(sc.describe(sc.weekly('10:00', [0, 2]), NOW), 'Пн, Ср · 10:00')
        self.assertEqual(sc.describe(sc.once(datetime(2026, 11, 15, 9, 0)), NOW), 'Один раз · завтра 09:00')


class Secrets(unittest.TestCase):
    def test_known_formats(self):
        cases = {
            'sk-proj-' + 'Ab1' * 10: 'API-ключ',
            'ghp_' + 'a' * 36: 'Токен GitHub',
            'AKIA' + 'ABCDEFGHIJKLMNOP': 'Ключ AWS',
            'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N': 'JWT-токен',
            '-----BEGIN RSA PRIVATE KEY-----\nMIIE...': 'Приватный ключ',
            'password = Tr0ub4dor&3': 'Пароль',
            'Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123': 'Токен доступа',
            '4111 1111 1111 1111': 'Банковская карта',
            'LV80BANK0000435195001': 'IBAN',
        }
        for text, kind in cases.items():
            self.assertEqual(classify(text), kind, text)

    def test_checksums(self):
        self.assertTrue(luhn_ok('4111111111111111'))
        self.assertFalse(luhn_ok('4111111111111112'))
        self.assertTrue(iban_ok('GB82 WEST 1234 5698 7654 32'))
        self.assertFalse(iban_ok('GB82 WEST 1234 5698 7654 33'))

    def test_password_heuristic(self):
        self.assertEqual(classify('Xk9#mP2$vL7q'), 'Возможный пароль')
        self.assertIsNone(classify('Xk9#mP2$vL7q', heuristic=False))

    def test_ordinary_text_is_not_secret(self):
        for t in ('Привет, как дела?', 'https://example.com/path?q=1&x=Ab3$', 'user@example.com', 'C:\\Users\\me\\file.txt',
                  'hello world', 'Встреча в 16:30 у метро', '1234567890123456', 'README.md', '2026-11-14', 'Hello', 'snake_case_name_here'):
            self.assertIsNone(classify(t), t)


if __name__ == '__main__':
    unittest.main()
