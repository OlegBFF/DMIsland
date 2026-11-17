"""Устойчивость: битая база, имена аудиоустройств без pycaw, лимит повторов в диагностике."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import db as dbmod
from core import diagnostics
from system import audio_names


class BrokenDatabase(unittest.TestCase):
    def test_garbage_file_is_set_aside_and_new_db_works(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'island.db'
            p.write_bytes(b'this is definitely not sqlite' * 50)
            Path(str(p) + '-wal').write_bytes(b'stale wal')
            d = dbmod.open_database(p)
            self.assertEqual(d.row('PRAGMA user_version')[0], len(dbmod.MIGRATIONS))
            self.assertTrue(any('corrupt' in f.name for f in Path(t).iterdir()))
            self.assertFalse(Path(str(p) + '-wal').exists() and b'stale' in Path(str(p) + '-wal').read_bytes())
            d.close()

    def test_failed_init_closes_connection(self):
        closed = []
        real = sqlite3.connect

        def spy(*a, **k):
            con = real(*a, **k)
            class W:
                def __getattr__(s, n):
                    return getattr(con, n)
                def close(s):
                    closed.append(1)
                    con.close()
            return W()
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'x.db'
            p.write_bytes(b'garbage' * 100)
            with mock.patch.object(dbmod.sqlite3, 'connect', spy):
                with self.assertRaises(sqlite3.DatabaseError):
                    dbmod.Database(p)
            self.assertTrue(closed, 'соединение должно закрываться, иначе Windows не даст переименовать файл')

    def test_falls_back_to_memory_when_cannot_recover(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'island.db'
            p.write_bytes(b'garbage' * 100)
            with mock.patch.object(dbmod, '_set_aside', lambda path: False):
                d = dbmod.open_database(p)
            self.assertEqual(d.path, ':memory:')
            d.close()

    def test_keeps_only_three_corrupt_copies(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'island.db'
            for i in range(5):
                (Path(t) / f'island.corrupt-{i}.db').write_bytes(b'x')
            p.write_bytes(b'garbage' * 100)
            dbmod._set_aside(p)
            self.assertLessEqual(len(list(Path(t).glob('island.corrupt-*.db'))), 3)


class FakeKey:
    def __init__(s, fmtid, pid):
        s.fmtid, s.pid = fmtid, pid


class FakeVal:
    def __init__(s, v):
        s.v, s.cleared = v, False
    def GetValue(s):
        return s.v
    def clear(s):
        s.cleared = True


class FakeStore:
    """Хранилище, где «плохие» свойства (как 63/64 в логе) падают, а FriendlyName читается."""
    def __init__(s):
        s.keys = [FakeKey('{11111111-0000-0000-0000-000000000000}', 1),
                  FakeKey('{A45C254E-DF1C-4EFD-8020-67D146A850E0}', 2),
                  FakeKey('{A45C254E-DF1C-4EFD-8020-67D146A850E0}', 14)]
        s.read = []
    def GetCount(s):
        return len(s.keys)
    def GetAt(s, j):
        return s.keys[j]
    def GetValue(s, pk):
        s.read.append(pk.pid)
        if pk.pid != 14:
            raise OSError('COMError')
        return FakeVal('Динамики (Realtek)')


class FakeDev:
    def __init__(s, did, store):
        s._id, s._store = did, store
    def OpenPropertyStore(s, mode):
        return s._store
    def GetId(s):
        return s._id


class FakeEnum:
    def __init__(s, devs):
        s.devs = devs
    def EnumAudioEndpoints(s, flow, state):
        items = s.devs.get(flow, [])
        class C:
            def GetCount(c): return len(items)
            def Item(c, i): return items[i]
        return C()


class AudioNames(unittest.TestCase):
    def test_reads_only_friendly_name(self):
        st = FakeStore()
        self.assertEqual(audio_names.friendly_name(FakeDev('a', st)), 'Динамики (Realtek)')
        self.assertEqual(st.read, [14], 'остальные свойства трогать не нужно — именно они давали COMError')

    def test_active_device_names_covers_both_flows(self):
        enum = FakeEnum({0: [FakeDev('out1', FakeStore())], 1: [FakeDev('in1', FakeStore())]})
        with mock.patch.object(audio_names, '_legacy_only', False):
            self.assertEqual(audio_names.active_device_names(enum), {'out1': 'Динамики (Realtek)', 'in1': 'Динамики (Realtek)'})


class Diagnostics(unittest.TestCase):
    def test_repeats_are_limited(self):
        diagnostics._seen.clear()
        res = [diagnostics._once('same message') for _ in range(6)]
        self.assertEqual(res, [True] * 3 + [False] * 3)


if __name__ == '__main__':
    unittest.main()
