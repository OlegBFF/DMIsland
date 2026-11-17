"""Хранилища на SQLite: полка файлов, напоминания, диалоги ИИ. Без Qt."""
import json
import time
from datetime import datetime
from pathlib import Path
from core import schedule


class ShelfStore:
    def __init__(s, db):
        s.db = db

    def paths(s):
        return [r['path'] for r in s.db.rows("SELECT path FROM shelf ORDER BY id")]

    def add(s, paths) -> int:
        n = 0
        with s.db.tx():
            for p in paths:
                if p and not p.startswith('\\\\') and not p.startswith('//'):
                    n += s.db.run("INSERT OR IGNORE INTO shelf(path, added) VALUES(?,?)", (p, time.time())).rowcount
        return n

    def remove(s, path: str):
        s.db.run("DELETE FROM shelf WHERE path=?", (path,))

    def clear(s):
        s.db.run("DELETE FROM shelf")

    def remove_missing(s) -> int:
        gone = [p for p in s.paths() if not Path(p).exists()]
        for p in gone:
            s.remove(p)
        return len(gone)


class ReminderStore:
    def __init__(s, db):
        s.db = db

    @staticmethod
    def _ts(dt):
        return dt.timestamp() if dt else None

    def _pack(s, r, now=None):
        d = dict(r)
        d['rule'] = json.loads(d['rule'])
        d['due'] = datetime.fromtimestamp(d['next_due']) if d['next_due'] else None
        return d

    def add(s, text: str, rule: dict, now: datetime = None) -> int:
        now = now or datetime.now()
        schedule.validate(rule)
        nxt = schedule.next_occurrence(rule, now)
        if nxt is None:
            raise ValueError('Это время уже прошло')
        return s.db.run("INSERT INTO reminders(text,rule,next_due,enabled,created) VALUES(?,?,?,1,?)",
                        (text.strip() or 'Напоминание', json.dumps(rule, ensure_ascii=False), s._ts(nxt), time.time())).lastrowid

    def update(s, rid: int, text: str, rule: dict, now: datetime = None):
        now = now or datetime.now()
        schedule.validate(rule)
        nxt = schedule.next_occurrence(rule, now)
        if nxt is None:
            raise ValueError('Это время уже прошло')
        s.db.run("UPDATE reminders SET text=?, rule=?, next_due=?, enabled=1 WHERE id=?",
                 (text.strip() or 'Напоминание', json.dumps(rule, ensure_ascii=False), s._ts(nxt), rid))

    def delete(s, rid: int):
        s.db.run("DELETE FROM reminders WHERE id=?", (rid,))

    def get(s, rid: int):
        r = s.db.row("SELECT * FROM reminders WHERE id=?", (rid,))
        return s._pack(r) if r else None

    def all(s):
        rows = s.db.rows("SELECT * FROM reminders ORDER BY enabled DESC, next_due IS NULL, next_due, id")
        return [s._pack(r) for r in rows]

    def set_enabled(s, rid: int, on: bool, now: datetime = None) -> bool:
        """Включает/выключает; False, если включить нельзя (одноразовое уже в прошлом)."""
        r = s.get(rid)
        if not r:
            return False
        if not on:
            s.db.run("UPDATE reminders SET enabled=0 WHERE id=?", (rid,))
            return True
        nxt = schedule.next_occurrence(r['rule'], now or datetime.now())
        if nxt is None:
            return False
        s.db.run("UPDATE reminders SET enabled=1, next_due=? WHERE id=?", (s._ts(nxt), rid))
        return True

    def due(s, now: datetime = None):
        now = now or datetime.now()
        rows = s.db.rows("SELECT * FROM reminders WHERE enabled=1 AND next_due IS NOT NULL AND next_due<=? ORDER BY next_due",
                         (now.timestamp(),))
        return [s._pack(r) for r in rows]

    def mark_fired(s, rid: int, now: datetime = None):
        """После срабатывания: повторяющееся уходит на следующий раз, одноразовое выключается."""
        now = now or datetime.now()
        r = s.get(rid)
        if not r:
            return
        nxt = schedule.next_occurrence(r['rule'], now)
        s.db.run("UPDATE reminders SET next_due=?, enabled=?, last_fired=?, fired=fired+1 WHERE id=?",
                 (s._ts(nxt), int(nxt is not None), now.timestamp(), rid))

    def snooze(s, rid: int, minutes: int, now: datetime = None):
        now = now or datetime.now()
        s.db.run("UPDATE reminders SET next_due=?, enabled=1 WHERE id=?", (now.timestamp() + minutes * 60, rid))

    def import_legacy(s, old: list, now: datetime = None) -> int:
        """Старые напоминания из config.json вели себя как «каждый день в HH:MM»."""
        n = 0
        for r in old or []:
            try:
                h, m = str(r.get('time', '')).split(':')
                s.add(r.get('text') or 'Напоминание', schedule.daily(f"{int(h):02d}:{int(m):02d}"), now)
                n += 1
            except (ValueError, AttributeError):
                continue
        return n


class ChatStore:
    def __init__(s, db):
        s.db = db

    def new_conv(s) -> int:
        now = time.time()
        return s.db.run("INSERT INTO chat_convs(title,created,updated) VALUES('',?,?)", (now, now)).lastrowid

    def latest_conv(s):
        r = s.db.row("SELECT id FROM chat_convs ORDER BY updated DESC, id DESC LIMIT 1")
        return r['id'] if r else None

    def messages(s, conv_id: int):
        """Реплики диалога. role: user / assistant / action (строка-результат команды, модели не отправляется).
        У сообщения может быть attach — список вложений [{'kind': 'shot'|'ocr'|'clip', 'label', 'path'?, 'text'?}]."""
        out = []
        for r in s.db.rows("SELECT role, content, attach FROM chat_msgs WHERE conv_id=? ORDER BY id", (conv_id,)):
            m = {'role': r['role'], 'content': r['content']}
            if r['attach']:
                try:
                    m['attach'] = json.loads(r['attach'])
                except ValueError:
                    pass
            out.append(m)
        return out

    def add(s, conv_id: int, role: str, content: str, attach=None):
        now = time.time()
        with s.db.tx():
            s.db.run("INSERT INTO chat_msgs(conv_id,role,content,ts,attach) VALUES(?,?,?,?,?)",
                     (conv_id, role, content, now, json.dumps(attach, ensure_ascii=False) if attach else None))
            s.db.run("UPDATE chat_convs SET updated=?, title=CASE WHEN title='' AND ?='user' THEN ? ELSE title END WHERE id=?",
                     (now, role, content.strip().replace('\n', ' ')[:60], conv_id))

    def pop_last(s, conv_id: int, role: str):
        """Убирает последнее сообщение роли (например, неудавшийся запрос пользователя)."""
        s.db.run("DELETE FROM chat_msgs WHERE id=(SELECT id FROM chat_msgs WHERE conv_id=? AND role=? ORDER BY id DESC LIMIT 1)",
                 (conv_id, role))

    def convs(s, limit: int = 15):
        return [dict(r) for r in s.db.rows(
            "SELECT c.id, c.title, c.updated FROM chat_convs c WHERE EXISTS(SELECT 1 FROM chat_msgs m WHERE m.conv_id=c.id) "
            "ORDER BY c.updated DESC LIMIT ?", (limit,))]

    def delete_conv(s, conv_id: int):
        s.db.run("DELETE FROM chat_convs WHERE id=?", (conv_id,))


class NotificationStore:
    """История уведомлений: дедупликация, приоритеты, прочитано, отложено."""
    DUP_WINDOW = 20.0       # секунд: одинаковый текст от того же приложения считается повтором

    def __init__(s, db):
        s.db = db

    def add(s, source, app_id, app, title, body, priority, now=None, win_id=None):
        """Возвращает (id, новое_ли). Повтор не создаёт новой записи, а увеличивает счётчик."""
        now = now or time.time()
        with s.db.tx():
            if win_id is not None:
                r = s.db.row("SELECT id FROM notifications WHERE source=? AND win_id=?", (source, win_id))
                if r:
                    return r['id'], False
            r = s.db.row("SELECT id FROM notifications WHERE source=? AND app_id=? AND app=? AND title=? AND body=? AND created>?",
                         (source, app_id, app, title, body, now - s.DUP_WINDOW))
            if r:
                s.db.run("UPDATE notifications SET count=count+1, created=?, read=0 WHERE id=?", (now, r['id']))
                return r['id'], False
            cur = s.db.run("INSERT INTO notifications(source,app_id,app,title,body,priority,created,win_id) VALUES(?,?,?,?,?,?,?,?)",
                           (source, app_id, app, title, body, priority, now, win_id))
            return cur.lastrowid, True

    def get(s, nid):
        r = s.db.row("SELECT * FROM notifications WHERE id=?", (nid,))
        return dict(r) if r else None

    def items(s, priority=None, query='', unread_only=False, snoozed_only=False, limit=300, now=None):
        now = now or time.time()
        where, args = [], []
        if priority:
            where.append("priority=?")
            args.append(priority)
        if unread_only:
            where.append("read=0")
        if snoozed_only:
            where.append("snooze_until IS NOT NULL AND snooze_until>?")
            args.append(now)
        for w in query.casefold().split():
            where.append("(cf(app) LIKE ? OR cf(title) LIKE ? OR cf(body) LIKE ?)")
            args += [f"%{w}%"] * 3
        sql = "SELECT * FROM notifications" + (" WHERE " + " AND ".join(where) if where else "")
        return [dict(r) for r in s.db.rows(sql + " ORDER BY created DESC LIMIT ?", (*args, limit))]

    def unread_counts(s, now=None) -> dict:
        now = now or time.time()
        out = {'important': 0, 'system': 0, 'normal': 0}
        for r in s.db.rows("SELECT priority, COUNT(*) c FROM notifications WHERE read=0 AND (snooze_until IS NULL OR snooze_until<=?) GROUP BY priority", (now,)):
            out[r['priority']] = r['c']
        return out

    def mark_read(s, nid=None, priority=None):
        q, a = "UPDATE notifications SET read=1", []
        cond = []
        if nid is not None:
            cond.append("id=?")
            a.append(nid)
        if priority:
            cond.append("priority=?")
            a.append(priority)
        s.db.run(q + (" WHERE " + " AND ".join(cond) if cond else ""), a)

    _APP = "cf(COALESCE(NULLIF(app_id,''),app))"

    def mark_read_app(s, key: str):
        s.db.run(f"UPDATE notifications SET read=1 WHERE {s._APP}=?", (key.casefold(),))

    def delete_app(s, key: str):
        s.db.run(f"DELETE FROM notifications WHERE {s._APP}=?", (key.casefold(),))

    def snooze(s, nid, until):
        s.db.run("UPDATE notifications SET snooze_until=?, read=1 WHERE id=?", (until, nid))

    def due_snoozed(s, now=None):
        """Отложенные, время которых пришло: возвращаются снова непрочитанными."""
        now = now or time.time()
        rows = s.db.rows("SELECT * FROM notifications WHERE snooze_until IS NOT NULL AND snooze_until<=? ORDER BY snooze_until", (now,))
        out = [dict(r) for r in rows]
        if out:
            s.db.run(f"UPDATE notifications SET snooze_until=NULL, read=0 WHERE id IN ({','.join('?' * len(out))})", [r['id'] for r in out])
        return out

    def delete(s, nid):
        s.db.run("DELETE FROM notifications WHERE id=?", (nid,))

    def clear(s, priority=None, keep_unread_important=False):
        cond, a = [], []
        if priority:
            cond.append("priority=?")
            a.append(priority)
        if keep_unread_important:
            cond.append("NOT (priority='important' AND read=0)")
        s.db.run("DELETE FROM notifications" + (" WHERE " + " AND ".join(cond) if cond else ""), a)

    def prune(s, keep_days=30, max_items=2000, now=None) -> int:
        now = now or time.time()
        n = s.db.run("DELETE FROM notifications WHERE created<? AND snooze_until IS NULL", (now - keep_days * 86400,)).rowcount
        extra = s.db.row("SELECT COUNT(*) c FROM notifications")['c'] - max_items
        if extra > 0:
            n += s.db.run("DELETE FROM notifications WHERE id IN (SELECT id FROM notifications ORDER BY created ASC LIMIT ?)", (extra,)).rowcount
        return n
