"""Тесты WorkAreaGuard на «поддельной» Windows: панель задач 40 px снизу."""
import json
import tempfile
import unittest
from pathlib import Path

from core.win32 import WorkAreaGuard

SCREEN_WA = (0, 0, 1920, 1040)       # исходная область: панель задач снизу


class FakeWin:
    def __init__(self, wa=SCREEN_WA):
        self.wa = wa
        self.history = []

    def get(self):
        return self.wa

    def set(self, r):
        self.wa = tuple(r)
        self.history.append(tuple(r))
        return True


class WorkArea(unittest.TestCase):
    def setUp(self):
        self.win = FakeWin()
        self.path = Path(tempfile.mkdtemp()) / 'state.json'
        self.g = WorkAreaGuard(self.path, self.win.get, self.win.set)

    def test_reserve_keeps_taskbar_and_restore_returns_original(self):
        self.g.reserve(40)
        self.assertEqual(self.win.wa, (0, 40, 1920, 1040))        # низ (панель задач) не затронут
        self.g.restore()
        self.assertEqual(self.win.wa, SCREEN_WA)                  # раньше сюда писался весь экран (0,0,1920,1080)
        self.assertFalse(self.path.exists())

    def test_repeated_reserve_is_idempotent(self):
        self.g.reserve(40)
        self.g.reserve(40)
        self.g.reserve(60)
        self.assertEqual(self.win.wa, (0, 60, 1920, 1040))
        self.g.restore()
        self.assertEqual(self.win.wa, SCREEN_WA)

    def test_taskbar_on_top_and_left(self):
        for wa, exp in (((0, 48, 1920, 1080), (0, 88, 1920, 1080)), ((60, 0, 1920, 1080), (60, 40, 1920, 1080))):
            win = FakeWin(wa)
            g = WorkAreaGuard(self.path, win.get, win.set)
            g.reserve(40)
            self.assertEqual(win.wa, exp)
            g.restore()
            self.assertEqual(win.wa, wa)

    def test_crash_recovery_on_next_start(self):
        self.g.reserve(40)                                        # «процесс упал» — restore() не вызывался
        self.assertTrue(self.path.exists())
        g2 = WorkAreaGuard(self.path, self.win.get, self.win.set)
        self.assertTrue(g2.recover())
        self.assertEqual(self.win.wa, SCREEN_WA)
        self.assertFalse(self.path.exists())

    def test_recovery_does_not_clobber_foreign_change(self):
        self.g.reserve(40)
        self.win.wa = (0, 0, 1280, 680)                           # сменилось разрешение / кто-то другой поменял область
        g2 = WorkAreaGuard(self.path, self.win.get, self.win.set)
        self.assertFalse(g2.recover())
        self.assertEqual(self.win.wa, (0, 0, 1280, 680))

    def test_restore_does_not_clobber_foreign_change(self):
        self.g.reserve(40)
        self.win.wa = (0, 0, 1280, 680)
        self.g.restore()
        self.assertEqual(self.win.wa, (0, 0, 1280, 680))

    def test_foreign_change_becomes_new_original(self):
        self.g.reserve(40)
        self.win.wa = (0, 0, 1280, 680)                           # пользователь сменил разрешение, остров переставляет резерв
        self.g.reserve(40)
        self.assertEqual(self.win.wa, (0, 40, 1280, 680))
        self.g.restore()
        self.assertEqual(self.win.wa, (0, 0, 1280, 680))

    def test_state_written_before_system_change(self):
        seen = []
        orig = self.win.set

        def spy(r):
            seen.append(json.loads(self.path.read_text()))
            return orig(r)
        g = WorkAreaGuard(self.path, self.win.get, spy)
        g.reserve(40)
        self.assertEqual(seen[0]['orig'], list(SCREEN_WA))

    def test_restore_without_reserve_is_noop(self):
        self.assertFalse(self.g.restore())
        self.assertEqual(self.win.history, [])


if __name__ == '__main__':
    unittest.main()
