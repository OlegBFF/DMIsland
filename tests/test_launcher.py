"""Лаунчер: выбор Python, установка библиотек, запуск процесса и отчёт о сбое — без tkinter и без Windows."""
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import launcher as L


def make_paths(root: Path) -> L.Paths:
    return L.Paths(base=root / 'app', appdata=root / 'appdata', localappdata=root / 'local')


def make_project(root: Path, main_code: str) -> Path:
    proj = root / 'app'
    (proj / 'core').mkdir(parents=True)
    (proj / 'core' / 'app.py').write_text('', 'utf-8')
    (proj / 'main.py').write_text(textwrap.dedent(main_code), 'utf-8')
    return proj


class PythonChoice(unittest.TestCase):
    def test_prefers_313_then_older_and_requires_64bit(self):
        vers = {'a': (3, 9, 1, 64), 'b': (3, 12, 4, 64), 'c': (3, 13, 1, 32), 'd': (3, 14, 0, 64), 'e': None, 'f': (3, 13, 0, 64)}
        cmd, v = L.find_python([[k] for k in vers], probe=lambda c: vers[c[0]])
        self.assertEqual(cmd, ['f'])
        vers.pop('f')
        self.assertEqual(L.find_python([[k] for k in vers], probe=lambda c: vers[c[0]])[0], ['b'])

    def test_falls_back_to_newer_unlisted_version(self):
        self.assertEqual(L.find_python([['x']], probe=lambda c: (3, 14, 0, 64))[1][:2], (3, 14))

    def test_none_when_nothing_suitable(self):
        self.assertIsNone(L.find_python([['x'], ['y']], probe=lambda c: (3, 8, 0, 64) if c == ['x'] else None))

    def test_probe_real_interpreter(self):
        v = L.probe_python([sys.executable])
        self.assertEqual(v[:2], sys.version_info[:2])
        self.assertIsNone(L.probe_python(['definitely-not-a-python-binary']))


class Requirements(unittest.TestCase):
    TEXT = 'PySide6\npycaw  # audio\n\n# comment\nwinrt-Windows.Foundation\nPillow>=10\n'

    def test_parse_and_stamp(self):
        self.assertEqual(L.parse_requirements(self.TEXT), ['PySide6', 'pycaw', 'winrt-Windows.Foundation', 'Pillow>=10'])
        a = L.req_stamp(self.TEXT, (3, 13, 1, 64))
        self.assertEqual(a, L.req_stamp(self.TEXT + '\n# ещё комментарий\n', (3, 13, 9, 64)))      # комментарии и micro не важны
        self.assertNotEqual(a, L.req_stamp(self.TEXT + 'numpy\n', (3, 13, 1, 64)))
        self.assertNotEqual(a, L.req_stamp(self.TEXT, (3, 12, 1, 64)))

    def test_critical(self):
        for x in ('PySide6', 'pycaw>=2024', 'comtypes==1.4.8', 'psutil', 'PySide6[all]'):
            self.assertTrue(L.is_critical(x), x)
        for x in ('pillow', 'mss', 'winrt-Windows.Media.Control', 'pyaudiowpatch'):
            self.assertFalse(L.is_critical(x), x)

    def _paths(self, t):
        return make_paths(Path(t))

    def test_bulk_install_ok_writes_stamp(self):
        with tempfile.TemporaryDirectory() as t:
            p, calls = self._paths(t), []
            failed = L.install_requirements('py', 'req.txt', self.TEXT, (3, 13, 0, 64), p, lambda s: None,
                                            runner=lambda cmd, log: calls.append(cmd) or 0)
            self.assertEqual(failed, [])
            self.assertTrue(any('-r' in c for c in calls))
            self.assertEqual(p.stamp.read_text('utf-8'), L.req_stamp(self.TEXT, (3, 13, 0, 64)))

    def test_optional_failure_is_reported_not_fatal(self):
        def runner(cmd, log):
            if '-r' in cmd:
                return 1
            return 1 if 'winrt-Windows.Foundation' in cmd else 0
        with tempfile.TemporaryDirectory() as t:
            p = self._paths(t)
            failed = L.install_requirements('py', 'req.txt', self.TEXT, (3, 13, 0, 64), p, lambda s: None, runner=runner)
            self.assertEqual(failed, ['winrt-Windows.Foundation'])
            self.assertTrue(p.stamp.exists())

    def test_critical_failure_raises_and_no_stamp(self):
        def runner(cmd, log):
            return 1 if ('-r' in cmd or 'PySide6' in cmd) else 0
        with tempfile.TemporaryDirectory() as t:
            p = self._paths(t)
            with self.assertRaises(L.SetupError) as cm:
                L.install_requirements('py', 'req.txt', self.TEXT, (3, 13, 0, 64), p, lambda s: None, runner=runner)
            self.assertIn('PySide6', str(cm.exception))
            self.assertFalse(p.stamp.exists())

    def test_needs_install_without_stamp(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertTrue(L.needs_install(sys.executable, self.TEXT, (3, 13, 0, 64), self._paths(t)))


class ProjectDiscovery(unittest.TestCase):
    def test_finds_main_next_to_or_inside_subfolder(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            self.assertIsNone(L.Paths(base=root / 'nothing').project())
            proj = make_project(root, 'pass')
            self.assertEqual(make_paths(root).project(), proj)
            inner = root / 'outer'
            (inner / 'Island' / 'core').mkdir(parents=True)
            (inner / 'Island' / 'main.py').write_text('', 'utf-8')
            (inner / 'Island' / 'core' / 'app.py').write_text('', 'utf-8')
            self.assertEqual(L.Paths(base=inner).project(), inner / 'Island')


class Supervising(unittest.TestCase):
    def run_main(self, code):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        proj = make_project(root, code)
        p = make_paths(root)
        run = L.Run(p, sys.executable, proj).start()
        rc = run.wait()
        return p, run, rc, run.report(rc)

    def test_clean_exit_is_silent(self):
        p, run, rc, rep = self.run_main('print("hello")')
        self.assertEqual(rc, 0)
        self.assertFalse(L.should_report(rc, rep))

    def test_python_traceback_is_reported_with_cause(self):
        p, run, rc, rep = self.run_main('import sys\nprint("starting", file=sys.stderr)\nraise RuntimeError("boom 42")')
        self.assertNotEqual(rc, 0)
        self.assertTrue(L.should_report(rc, rep))
        self.assertIn('boom 42', rep)
        self.assertIn('run.log', rep)

    def test_island_log_and_crash_log_only_new_part(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        root = Path(t.name)
        proj = make_project(root, textwrap.dedent('''
            import os, sys
            d = os.environ["APPDATA"]
            open(os.path.join(d, "Island", "island.log"), "a").write("NEW-LINE-FROM-RUN\\n")
            sys.exit(5)
        '''))
        p = make_paths(root)
        p.data.mkdir(parents=True)
        p.island_log.write_text('OLD-LINE-BEFORE\n', 'utf-8')
        import os
        old = os.environ.get('APPDATA')
        os.environ['APPDATA'] = str(root / 'appdata')
        try:
            run = L.Run(p, sys.executable, proj).start()
            rc = run.wait()
        finally:
            if old is None:
                os.environ.pop('APPDATA')
            else:
                os.environ['APPDATA'] = old
        rep = run.report(rc)
        self.assertIn('NEW-LINE-FROM-RUN', rep)
        self.assertNotIn('OLD-LINE-BEFORE', rep)
        self.assertTrue(L.should_report(rc, rep))

    def test_killed_from_outside_without_logs_is_quiet_but_native_crash_is_not(self):
        self.assertFalse(L.should_report(1, '=== header ==='))
        self.assertTrue(L.should_report(0xC0000005, '=== header ==='))
        self.assertFalse(L.should_report(0, 'x\n--- y ---\nz'))

    def test_describe_exit(self):
        self.assertIn('access violation', L.describe_exit(3221225477))
        self.assertIn('0xC0000005', L.describe_exit(0xC0000005))
        self.assertEqual(L.describe_exit(3), '3')

    def test_read_since_handles_truncated_file_and_limits_lines(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / 'x.log'
            f.write_text('\n'.join(f'line{i}' for i in range(100)), 'utf-8')
            out = L.read_since(f, 0, 10)
            self.assertIn('line99', out)
            self.assertNotIn('line50', out)
            self.assertIn('пропущено', out)
            self.assertIn('line0', L.read_since(f, 10 ** 9, 200))              # файл обрезали — читаем сначала
            self.assertEqual(L.read_since(Path(t) / 'missing.log', 0), '')


class Policy(unittest.TestCase):
    def test_crash_loop_stops_auto_restart(self):
        pol = L.RestartPolicy()
        self.assertTrue(pol.allow_auto())
        for t in (0, 10, 20):
            pol.record(t)
        self.assertFalse(pol.allow_auto())
        pol.record(1000)                                                     # старые сбои вышли из окна
        self.assertTrue(pol.allow_auto())


if __name__ == '__main__':
    unittest.main()
