"""История буфера обмена в SQLite: поиск, избранное, защита секретных данных. Без Qt."""
import hashlib
import time
from pathlib import Path
from core.secrets_detect import classify
from core.security import dpapi_decrypt, dpapi_encrypt


def _like(q: str) -> str:
    return '%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def _rm(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


class ClipStore:
    MAX_TEXT = 500_000

    def __init__(s, db, encrypt=dpapi_encrypt, decrypt=dpapi_decrypt, remove_file=_rm, **opts):
        s.db, s.encrypt, s.decrypt, s.remove_file = db, encrypt, decrypt, remove_file
        s.max_items = 300
        s.keep_days = 30
        s.secret_ttl = 120          # секунд хранения секретных данных
        s.secret_policy = 'mask'    # mask — хранить зашифрованно и скрывать, skip — не хранить совсем
        s.heuristic = True
        s.configure(**opts)

    def configure(s, **opts):
        for k, v in opts.items():
            if hasattr(s, k) and v is not None:
                setattr(s, k, v)

    # ---------- добавление ----------
    def add_text(s, text: str, now: float = None):
        """Возвращает (id | None, тип секрета | None). None вместо id — запись не сохранена."""
        t = text.strip()
        if not t or len(t) > s.MAX_TEXT:
            return None, None
        now = now or time.time()
        h = hashlib.sha1(t.encode('utf-8', 'ignore')).hexdigest()
        kind = classify(t, s.heuristic)
        if kind:
            if s.secret_policy == 'skip':
                return None, kind
            enc = s.encrypt(t)
            if not enc:                               # не удалось защитить — лучше не хранить вообще
                return None, kind
            with s.db.tx():
                s.db.run("DELETE FROM clip_items WHERE secret=1 AND hash=?", (h,))
                cur = s.db.run(
                    "INSERT INTO clip_items(kind,text,search,hash,secret,secret_enc,created,expires) "
                    "VALUES('text',?,'',?,1,?,?,?)",
                    (f"••••••••  {kind}", h, enc, now, now + s.secret_ttl))
            s.prune(now)
            return cur.lastrowid, kind
        with s.db.tx():
            row = s.db.row("SELECT id FROM clip_items WHERE kind='text' AND secret=0 AND hash=?", (h,))
            if row:
                s.db.run("UPDATE clip_items SET created=? WHERE id=?", (now, row['id']))
                rid = row['id']
            else:
                rid = s.db.run("INSERT INTO clip_items(kind,text,search,hash,created) VALUES('text',?,?,?,?)",
                               (t, t.casefold(), h, now)).lastrowid
        s.prune(now)
        return rid, None

    def add_file_item(s, kind: str, path: str, label: str, owned: bool = False, digest: str = None, now: float = None):
        """Картинка (kind='img') или файл/запись (kind='file'): в базе только путь и подпись."""
        now = now or time.time()
        digest = digest or hashlib.sha1(str(path).encode('utf-8', 'ignore')).hexdigest()
        with s.db.tx():
            row = s.db.row("SELECT id FROM clip_items WHERE kind=? AND hash=?", (kind, digest))
            if row:
                s.db.run("UPDATE clip_items SET created=?, path=?, text=? WHERE id=?", (now, str(path), label, row['id']))
                rid = row['id']
            else:
                rid = s.db.run("INSERT INTO clip_items(kind,text,search,path,owned,hash,created) VALUES(?,?,?,?,?,?,?)",
                               (kind, label, label.casefold(), str(path), int(owned), digest, now)).lastrowid
        s.prune(now)
        return rid

    # ---------- чтение ----------
    def items(s, query: str = '', favorites: bool = False, limit: int = 200):
        where, args = [], []
        if favorites:
            where.append('favorite=1')
        for w in query.casefold().split():
            where.append("search LIKE ? ESCAPE '\\'")
            args.append(_like(w))
        sql = "SELECT * FROM clip_items" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY favorite DESC, created DESC LIMIT ?"
        return [dict(r) for r in s.db.rows(sql, (*args, limit))]

    def get(s, item_id: int):
        r = s.db.row("SELECT * FROM clip_items WHERE id=?", (item_id,))
        return dict(r) if r else None

    def secret_value(s, item_id: int, now: float = None):
        r = s.db.row("SELECT secret_enc, expires FROM clip_items WHERE id=? AND secret=1", (item_id,))
        if not r or not r['secret_enc'] or (r['expires'] and r['expires'] <= (now or time.time())):
            return None
        return s.decrypt(r['secret_enc']) or None

    def touch(s, item_id: int):
        s.db.run("UPDATE clip_items SET used=?, uses=uses+1 WHERE id=?", (time.time(), item_id))

    def count(s) -> int:
        return s.db.row("SELECT COUNT(*) c FROM clip_items")['c']

    # ---------- изменение ----------
    def set_favorite(s, item_id: int, on: bool):
        s.db.run("UPDATE clip_items SET favorite=?, expires=CASE WHEN ? THEN NULL ELSE expires END WHERE id=?",
                 (int(on), int(on), item_id))

    def delete(s, item_id: int):
        s._delete_rows(s.db.rows("SELECT id, path, owned FROM clip_items WHERE id=?", (item_id,)))

    def clear(s, keep_favorites: bool = True):
        q = "SELECT id, path, owned FROM clip_items" + (" WHERE favorite=0" if keep_favorites else "")
        s._delete_rows(s.db.rows(q))

    def prune(s, now: float = None) -> int:
        """Удаляет просроченные секреты, старые записи и всё сверх лимита (избранное не трогает)."""
        now = now or time.time()
        victims = list(s.db.rows("SELECT id, path, owned FROM clip_items WHERE secret=1 AND expires IS NOT NULL AND expires<=?", (now,)))
        victims += s.db.rows("SELECT id, path, owned FROM clip_items WHERE favorite=0 AND created<?",
                             (now - s.keep_days * 86400,))
        extra = s.db.row("SELECT COUNT(*) c FROM clip_items WHERE favorite=0")['c'] - s.max_items
        if extra > 0:
            victims += s.db.rows("SELECT id, path, owned FROM clip_items WHERE favorite=0 ORDER BY created ASC LIMIT ?", (extra,))
        return s._delete_rows(victims)

    def _delete_rows(s, rows) -> int:
        seen = {}
        for r in rows:
            seen[r['id']] = r
        if not seen:
            return 0
        with s.db.tx():
            s.db.run(f"DELETE FROM clip_items WHERE id IN ({','.join('?' * len(seen))})", tuple(seen))
        for r in seen.values():
            if r['owned'] and r['path']:
                s.remove_file(r['path'])
        return len(seen)
