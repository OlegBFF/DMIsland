"""Тесты ядра (без Qt и Windows): python -m unittest discover -s tests -t ."""
import json
import tempfile
import unittest
from pathlib import Path

from core import config
from core.security import safe_math_eval
from core.utils import clamp


class SafeMathEval(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(safe_math_eval('245*18'), '4410')
        self.assertEqual(safe_math_eval('(1+2)*3'), '9')
        self.assertEqual(safe_math_eval('10/4'), '2.5')
        self.assertEqual(safe_math_eval('-5 + 2'), '-3')

    def test_rejects_non_math(self):
        for bad in ('__import__("os")', 'abs(1)', '1 if 1 else 2', 'a+1'):
            with self.assertRaises(Exception):
                safe_math_eval(bad)

    def test_limits(self):
        with self.assertRaises(ValueError):
            safe_math_eval('9' * 81)
        with self.assertRaises(ValueError):
            safe_math_eval('2**1000')


class Clamp(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(clamp(5), 1.0)
        self.assertEqual(clamp(-1), 0.0)
        self.assertEqual(clamp(0.4), 0.4)


class Config(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old = config.CFG_PATH
        config.CFG_PATH = self.tmp / 'Island' / 'config.json'
        config._LAST_CFG[0] = None

    def tearDown(self):
        config.CFG_PATH = self.old

    def test_defaults_when_missing(self):
        self.assertEqual(config.load_cfg()['theme'], config.DEFAULT_CFG['theme'])

    def test_roundtrip_and_no_plain_keys(self):
        c = config.load_cfg()
        c['city'] = 'Рига'
        c['ai_key'] = 'secret'            # открытые ключи не должны попасть на диск
        config.save_cfg(c)
        raw = json.loads(config.CFG_PATH.read_text('utf-8'))
        self.assertEqual(raw['city'], 'Рига')
        self.assertNotIn('ai_key', raw)
        self.assertEqual(config.load_cfg()['city'], 'Рига')

    def test_unknown_keys_do_not_break_defaults(self):
        config.CFG_PATH.parent.mkdir(parents=True)
        config.CFG_PATH.write_text(json.dumps({'city': 'Лондон'}), 'utf-8')
        c = config.load_cfg()
        self.assertEqual(c['city'], 'Лондон')
        self.assertIn('fps', c)


if __name__ == '__main__':
    unittest.main()
