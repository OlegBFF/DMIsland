"""SQLite-хранилище: история буфера, полка файлов, напоминания, диалоги ИИ.

Одно соединение на процесс, доступ защищён блокировкой — базой можно пользоваться из любых потоков.
Схема версионируется через PRAGMA user_version; битая база переименовывается, а не затирается.
"""
import os
import sqlite3
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from core.utils import log


MIGRATIONS = [
    [   # версия 1
        """CREATE TABLE clip_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            text TEXT NOT NULL DEFAULT '',
            search TEXT NOT NULL DEFAULT '',
            path TEXT,
            owned INTEGER NOT NULL DEFAULT 0,
            hash TEXT,
            favorite INTEGER NOT NULL DEFAULT 0,
            secret INTEGER NOT NULL DEFAULT 0,
            secret_enc TEXT,
            created REAL NOT NULL,
            used REAL,
            uses INTEGER NOT NULL DEFAULT 0,
            expires REAL)""",
        "CREATE INDEX clip_created ON clip_items(created DESC)",
        "CREATE INDEX clip_hash ON clip_items(hash)",
        """CREATE TABLE shelf(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            added REAL NOT NULL)""",
        """CREATE TABLE reminders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            rule TEXT NOT NULL,
            next_due REAL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created REAL NOT NULL,
            last_fired REAL,
            fired INTEGER NOT NULL DEFAULT 0)""",
        "CREATE INDEX rem_due ON reminders(enabled, next_due)",
        """CREATE TABLE chat_convs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            created REAL NOT NULL,
            updated REAL NOT NULL)""",
        """CREATE TABLE chat_msgs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conv_id INTEGER NOT NULL REFERENCES chat_convs(id) ON DELETE CASCADE,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            ts REAL NOT NULL)""",
        "CREATE INDEX chat_conv ON chat_msgs(conv_id, id)",
    ],
    [   # версия 2: центр уведомлений
        """CREATE TABLE notifications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            app_id TEXT NOT NULL DEFAULT '',
            app TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            priority TEXT NOT NULL DEFAULT 'normal',
            created REAL NOT NULL,
            read INTEGER NOT NULL DEFAULT 0,
            snooze_until REAL,
            win_id INTEGER,
            count INTEGER NOT NULL DEFAULT 1)""",
        "CREATE INDEX notif_created ON notifications(created DESC)",
        "CREATE INDEX notif_win ON notifications(win_id)",
    ],
    [   # версия 3: вложения в сообщениях ИИ (скриншот, текст с экрана, буфер) и вложения уведомлений
        "ALTER TABLE chat_msgs ADD COLUMN attach TEXT",
    ],
]


class Database:
    def __init__(s, path):
        s.path = str(path)
        if s.path != ':memory:':
            Path(s.path).parent.mkdir(parents=True, exist_ok=True)
        s._lock = threading.RLock()
        s._depth = 0
        s._con = sqlite3.connect(s.path, check_same_thread=False, isolation_level=None, timeout=5)
        s._con.row_factory = sqlite3.Row
        # lower() в SQLite не знает кириллицу — для регистронезависимого поиска есть cf()
        s._con.create_function('cf', 1, lambda v: v.casefold() if isinstance(v, str) else v, deterministic=True)
        for pr in ('journal_mode=WAL', 'synchronous=NORMAL', 'foreign_keys=ON'):
            try:
                s._con.execute(f'PRAGMA {pr}')
            except sqlite3.DatabaseError:
                pass
        try:
            s._migrate()
        except BaseException:
            # без этого соединение остаётся открытым, а Windows не даёт переименовать занятый файл —
            # битая база не откладывалась в сторону и остров падал при каждом запуске
            try:
                s._con.close()
            except sqlite3.Error:
                pass
            raise

    def _migrate(s):
        ver = s._con.execute('PRAGMA user_version').fetchone()[0]
        for i, stmts in enumerate(MIGRATIONS[ver:], start=ver + 1):
            with s.tx():
                for q in stmts:
                    s._con.execute(q)
                s._con.execute(f'PRAGMA user_version={i}')

    @contextmanager
    def tx(s):
        """Транзакция (вложенные вызовы присоединяются к внешней)."""
        with s._lock:
            if s._depth:
                s._depth += 1
                try:
                    yield
                finally:
                    s._depth -= 1
                return
            s._con.execute('BEGIN IMMEDIATE')
            s._depth = 1
            try:
                yield
                s._con.execute('COMMIT')
            except BaseException:
                s._con.execute('ROLLBACK')
                raise
            finally:
                s._depth = 0

    def run(s, sql, args=()):
        with s._lock:
            return s._con.execute(sql, args)

    def rows(s, sql, args=()):
        with s._lock:
            return s._con.execute(sql, args).fetchall()

    def row(s, sql, args=()):
        with s._lock:
            return s._con.execute(sql, args).fetchone()

    def close(s):
        with s._lock:
            try:
                s._con.close()
            except sqlite3.Error:
                pass


def _set_aside(p: Path) -> bool:
    """Откладывает повреждённую базу вместе с -wal/-shm (иначе старый журнал портит новую базу). True — файл освобождён."""
    stamp = int(time.time())
    moved = True
    for ext in ('', '-wal', '-shm'):
        src = Path(str(p) + ext)
        if not src.exists():
            continue
        try:
            if ext == '':
                os.replace(src, p.with_name(f"{p.stem}.corrupt-{stamp}{p.suffix}"))
            else:
                src.unlink()
        except OSError as ex:
            log(f"database: не удалось убрать {src.name}: {ex!r}")
            moved = moved and ext != ''
    # хранить только 3 последние копии
    try:
        old = sorted(p.parent.glob(f"{p.stem}.corrupt-*{p.suffix}"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in old[3:]:
            f.unlink(missing_ok=True)
    except OSError:
        pass
    return moved


def open_database(path) -> Database:
    """Открывает базу; если файл повреждён — откладывает его в сторону и создаёт чистую.
    Если и это не вышло, остров работает на базе в памяти: потеряется история, но запуск не сорвётся."""
    try:
        return Database(path)
    except sqlite3.DatabaseError as ex:
        log(f"database corrupted, recreating: {ex!r}")
    p = Path(path)
    _set_aside(p)
    try:
        return Database(path)
    except Exception:
        log("database: пересоздать не удалось, работаю в памяти\n" + traceback.format_exc())
        return Database(':memory:')
