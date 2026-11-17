"""Тесты хранилищ: буфер (поиск, избранное, секреты), полка, напоминания, диалоги."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from core import schedule
from core.clipstore import ClipStore
from core.db import MIGRATIONS, Database, open_database
from core.stores import ChatStore, ReminderStore, ShelfStore

FAKE_ENC = lambda t: 'enc:' + t[::-1]
FAKE_DEC = lambda t: t[4:][::-1] if t.startswith('enc:') else ''


def mk_store(**kw):
    removed = []
    st = ClipStore(Database(':memory:'), encrypt=FAKE_ENC, decrypt=FAKE_DEC, remove_file=removed.append, **kw)
    st.removed = removed
    return st


class Migrations(unittest.TestCase):
    def test_schema_and_reopen(self):
        d = Path(tempfile.mkdtemp()) / 'a.db'
        db = Database(d)
        db.run("INSERT INTO shelf(path, added) VALUES('x', 1)")
        db.close()
        db2 = Database(d)
        self.assertEqual(db2.row("SELECT COUNT(*) c FROM shelf")['c'], 1)
        self.assertEqual(db2.row('PRAGMA user_version')[0], len(MIGRATIONS))

    def test_upgrade_from_v1_keeps_data(self):
        import sqlite3
        d = Path(tempfile.mkdtemp()) / 'old.db'
        con = sqlite3.connect(d)
        for q in MIGRATIONS[0]:
            con.execute(q)
        con.execute("INSERT INTO shelf(path, added) VALUES('/keep/me', 1)")
        con.execute('PRAGMA user_version=1')
        con.commit()
        con.close()
        db = Database(d)                                           # применяется только миграция v2
        self.assertEqual(db.row("SELECT path FROM shelf")['path'], '/keep/me')
        db.run("INSERT INTO notifications(source,title,created) VALUES('windows','t',1)")

    def test_corrupt_file_is_moved_aside(self):
        d = Path(tempfile.mkdtemp()) / 'bad.db'
        d.write_bytes(b'this is not a sqlite database' * 50)
        db = open_database(d)
        db.run("INSERT INTO shelf(path, added) VALUES('x', 1)")
        self.assertTrue(any('corrupt' in p.name for p in d.parent.iterdir()))

    def test_rollback(self):
        db = Database(':memory:')
        with self.assertRaises(RuntimeError):
            with db.tx():
                db.run("INSERT INTO shelf(path, added) VALUES('x', 1)")
                raise RuntimeError
        self.assertEqual(db.row("SELECT COUNT(*) c FROM shelf")['c'], 0)


class Clip(unittest.TestCase):
    def test_dedupe_bumps_instead_of_duplicating(self):
        st = mk_store()
        a, _ = st.add_text('привет мир', now=100)
        st.add_text('другое', now=110)
        b, _ = st.add_text('привет мир', now=120)
        self.assertEqual(a, b)
        self.assertEqual(st.count(), 2)
        self.assertEqual(st.items()[0]['text'], 'привет мир')

    def test_search_is_case_insensitive_for_cyrillic(self):
        st = mk_store()
        st.add_text('Привет МИР')
        st.add_text('hello world')
        self.assertEqual([r['text'] for r in st.items('мир')], ['Привет МИР'])
        self.assertEqual(len(st.items('ПРИВ')), 1)
        self.assertEqual(len(st.items('привет мир')), 1)
        self.assertEqual(len(st.items('100%')), 0)               # % не работает как шаблон
        self.assertEqual(len(st.items('')), 2)

    def test_favorites_first_and_survive_clear(self):
        st = mk_store()
        a, _ = st.add_text('one', now=1)
        st.add_text('two', now=2)
        st.set_favorite(a, True)
        self.assertEqual(st.items()[0]['text'], 'one')
        self.assertEqual([r['text'] for r in st.items(favorites=True)], ['one'])
        st.clear(keep_favorites=True)
        self.assertEqual([r['text'] for r in st.items()], ['one'])

    def test_secret_masked_encrypted_not_searchable(self):
        st = mk_store()
        key = 'sk-' + 'a1B2c3D4e5F6g7H8i9J0k1L2'
        rid, kind = st.add_text(key, now=1000)
        self.assertEqual(kind, 'API-ключ')
        row = st.get(rid)
        self.assertNotIn(key, row['text'])
        self.assertNotIn(key, row['secret_enc'])                 # в базе лежит только шифртекст
        self.assertEqual(st.secret_value(rid, now=1001), key)
        self.assertEqual(st.items('a1b2c3'), [])
        self.assertEqual(st.secret_value(rid, now=1000 + 99999), None)   # просрочен

    def test_secret_expires_and_is_pruned(self):
        st = mk_store(secret_ttl=60)
        rid, _ = st.add_text('password: hunter2hunter2', now=1000)
        st.add_text('обычный текст', now=1010)
        st.prune(now=1000 + 61)
        self.assertIsNone(st.get(rid))
        self.assertEqual(st.count(), 1)

    def test_secret_policy_skip(self):
        st = mk_store(secret_policy='skip')
        rid, kind = st.add_text('ghp_' + 'x' * 36)
        self.assertIsNone(rid)
        self.assertEqual(kind, 'Токен GitHub')
        self.assertEqual(st.count(), 0)

    def test_secret_dropped_if_encryption_fails(self):
        st = ClipStore(Database(':memory:'), encrypt=lambda t: '', decrypt=lambda t: '')
        rid, kind = st.add_text('ghp_' + 'x' * 36)
        self.assertIsNone(rid)
        self.assertEqual(st.count(), 0)

    def test_favorite_secret_does_not_expire(self):
        st = mk_store(secret_ttl=60)
        rid, _ = st.add_text('password: hunter2hunter2', now=1000)
        st.set_favorite(rid, True)
        st.prune(now=1000 + 10_000)
        self.assertIsNotNone(st.get(rid))

    def test_limits_and_owned_file_cleanup(self):
        st = mk_store(max_items=3)
        st.add_file_item('img', '/tmp/a.png', 'img a', owned=True, digest='a', now=1)
        st.add_file_item('img', '/tmp/shot.png', 'user shot', owned=False, digest='b', now=2)
        for i in range(3, 6):
            st.add_text(f'text {i}', now=i)
        self.assertEqual(st.count(), 3)
        self.assertEqual(st.removed, ['/tmp/a.png'])             # свой файл удалён, пользовательский не тронут
        self.assertEqual([r['text'] for r in st.items()], ['text 5', 'text 4', 'text 3'])

    def test_retention_days(self):
        st = mk_store(keep_days=1)
        st.add_text('old', now=1000)
        st.add_text('new', now=1000 + 2 * 86400)
        self.assertEqual([r['text'] for r in st.items()], ['new'])


class Shelf(unittest.TestCase):
    def test_persist_dedupe_remove(self):
        d = Path(tempfile.mkdtemp()) / 'a.db'
        sh = ShelfStore(Database(d))
        self.assertEqual(sh.add(['/a/1.txt', '/a/2.txt', '/a/1.txt', '\\\\srv\\share\\x']), 2)   # UNC отброшен
        sh2 = ShelfStore(Database(d))                                                          # «перезапуск»
        self.assertEqual(sh2.paths(), ['/a/1.txt', '/a/2.txt'])
        sh2.remove('/a/1.txt')
        self.assertEqual(sh2.paths(), ['/a/2.txt'])

    def test_remove_missing(self):
        f = Path(tempfile.mkdtemp()) / 'real.txt'
        f.write_text('x')
        sh = ShelfStore(Database(':memory:'))
        sh.add([str(f), '/nonexistent/zzz'])
        self.assertEqual(sh.remove_missing(), 1)
        self.assertEqual(sh.paths(), [str(f)])


class Reminders(unittest.TestCase):
    NOW = datetime(2026, 11, 14, 12, 0, 0)

    def setUp(self):
        self.rs = ReminderStore(Database(':memory:'))

    def test_once_fires_once_then_disables(self):
        rid = self.rs.add('t', schedule.once(self.NOW + timedelta(minutes=5)), self.NOW)
        self.assertEqual(self.rs.due(self.NOW + timedelta(minutes=4)), [])
        due = self.rs.due(self.NOW + timedelta(minutes=5))
        self.assertEqual([r['id'] for r in due], [rid])
        self.rs.mark_fired(rid, self.NOW + timedelta(minutes=5))
        self.assertEqual(self.rs.due(self.NOW + timedelta(days=1)), [])
        r = self.rs.get(rid)
        self.assertFalse(r['enabled'])
        self.assertEqual(r['fired'], 1)

    def test_daily_repeats(self):
        rid = self.rs.add('t', schedule.daily('09:00'), self.NOW)
        self.assertEqual(self.rs.get(rid)['due'], datetime(2026, 11, 15, 9, 0))
        self.rs.mark_fired(rid, datetime(2026, 11, 15, 9, 0, 1))
        self.assertEqual(self.rs.get(rid)['due'], datetime(2026, 11, 16, 9, 0))
        self.assertTrue(self.rs.get(rid)['enabled'])

    def test_missed_recurring_does_not_burst(self):
        """Остров был выключен трое суток: ежедневное напоминание срабатывает один раз, а не три."""
        rid = self.rs.add('t', schedule.daily('09:00'), self.NOW)
        later = self.NOW + timedelta(days=3)
        self.assertEqual(len(self.rs.due(later)), 1)
        self.rs.mark_fired(rid, later)
        self.assertEqual(self.rs.due(later), [])
        self.assertGreater(self.rs.get(rid)['due'], later)

    def test_edit_toggle_delete_snooze(self):
        rid = self.rs.add('a', schedule.daily('09:00'), self.NOW)
        self.rs.update(rid, 'b', schedule.weekly('10:30', [0, 2]), self.NOW)
        r = self.rs.get(rid)
        self.assertEqual((r['text'], r['rule']['days']), ('b', [0, 2]))
        self.assertEqual(r['due'], datetime(2026, 11, 16, 10, 30))      # понедельник
        self.assertTrue(self.rs.set_enabled(rid, False))
        self.assertEqual(self.rs.due(self.NOW + timedelta(days=30)), [])
        self.assertTrue(self.rs.set_enabled(rid, True, self.NOW))
        self.rs.snooze(rid, 10, self.NOW)
        self.assertEqual(self.rs.get(rid)['due'], self.NOW + timedelta(minutes=10))
        self.rs.delete(rid)
        self.assertIsNone(self.rs.get(rid))

    def test_cannot_add_past_or_enable_past_once(self):
        with self.assertRaises(ValueError):
            self.rs.add('x', schedule.once(self.NOW - timedelta(minutes=1)), self.NOW)
        rid = self.rs.add('x', schedule.once(self.NOW + timedelta(minutes=1)), self.NOW)
        self.rs.mark_fired(rid, self.NOW + timedelta(minutes=1))
        self.assertFalse(self.rs.set_enabled(rid, True, self.NOW + timedelta(hours=1)))

    def test_legacy_import_is_daily(self):
        n = self.rs.import_legacy([{'text': 'Позвонить', 'time': '16:30', 'done_date': ''}, {'text': 'bad', 'time': 'xx'}], self.NOW)
        self.assertEqual(n, 1)
        r = self.rs.all()[0]
        self.assertEqual((r['rule']['type'], r['rule']['time']), ('daily', '16:30'))


class Chat(unittest.TestCase):
    def test_history_roundtrip_and_title(self):
        cs = ChatStore(Database(':memory:'))
        c = cs.new_conv()
        cs.add(c, 'user', 'Как дела?')
        cs.add(c, 'assistant', 'Отлично')
        cs.add(c, 'user', 'второй вопрос')
        self.assertEqual([m['role'] for m in cs.messages(c)], ['user', 'assistant', 'user'])
        self.assertEqual(cs.convs()[0]['title'], 'Как дела?')
        cs.pop_last(c, 'user')
        self.assertEqual(len(cs.messages(c)), 2)
        self.assertEqual(cs.latest_conv(), c)
        cs.delete_conv(c)
        self.assertEqual(cs.messages(c), [])


if __name__ == '__main__':
    unittest.main()
