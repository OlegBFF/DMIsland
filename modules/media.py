"""Медиа: WinRT-сессии плееров, тексты песен, слот плеера в острове."""
import asyncio
import json
import re
import threading
import time
import urllib.parse
from datetime import datetime
from datetime import timezone
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFontMetrics, QImage, QPixmap
from core.security import safe_urlopen
from core.utils import log
from ui.icons import dot_icon, vicon
from ui.themes import STYLE, wr
from ui.widgets import thumb


# ==================== МЕДИА И ТЕКСТЫ ПЕСЕН ====================
# ==================== МЕДИА: УМНОЕ ОПРЕДЕЛЕНИЕ ПЛЕЕРОВ ====================
# (подстрока AppUserModelId в нижнем регистре, название, цвет). Порядок важен: частные раньше общих.
PLAYER_DB = [
    ('yandexmusic', 'Яндекс Музыка', '#ffcc00'), ('yandex.music', 'Яндекс Музыка', '#ffcc00'),
    ('desktop.music', 'Яндекс Музыка', '#ffcc00'), ('yandexbrowser', 'Яндекс Браузер', '#fc3f1d'),
    ('spotify', 'Spotify', '#1ed760'), ('applemusic', 'Apple Music', '#fa2d48'), ('itunes', 'iTunes', '#fa2d48'),
    ('zunemusic', 'Медиаплеер', '#0a84ff'), ('zunevideo', 'Кино и ТВ', '#7c5cff'),
    ('ytmdesktop', 'YouTube Music', '#ff0033'), ('th-ch', 'YouTube Music', '#ff0033'),
    ('tidal', 'TIDAL', '#00ffff'), ('deezer', 'Deezer', '#a238ff'), ('amazonmusic', 'Amazon Music', '#25d1da'),
    ('sberzvuk', 'Звук', '#21a038'), ('zvuk', 'Звук', '#21a038'), ('vkmusic', 'VK Музыка', '#0077ff'),
    ('vlc', 'VLC', '#ff8800'), ('aimp', 'AIMP', '#2d9cdb'), ('foobar', 'foobar2000', '#9aa0a6'),
    ('musicbee', 'MusicBee', '#f5a623'), ('potplayer', 'PotPlayer', '#ffb300'), ('mpc-', 'MPC', '#9aa0a6'),
    ('plexamp', 'Plexamp', '#e5a00d'), ('netflix', 'Netflix', '#e50914'), ('telegram', 'Telegram', '#2aabee'),
    ('discord', 'Discord', '#5865f2'), ('msedge', 'Edge', '#0fb5ae'), ('edge', 'Edge', '#0fb5ae'),
    ('chrome', 'Chrome', '#4285f4'), ('firefox', 'Firefox', '#ff7139'), ('opera', 'Opera', '#ff1b2d'),
    ('brave', 'Brave', '#fb542b'), ('vivaldi', 'Vivaldi', '#ef3939'), ('zenbrowser', 'Zen', '#f76f53'),
    ('zen.exe', 'Zen', '#f76f53'), ('app.zen', 'Zen', '#f76f53'),
]


def player_info(app_id: str):
    """(красивое имя, цвет) плеера по AppUserModelId."""
    low = (app_id or '').lower()
    for key, name, col in PLAYER_DB:
        if key in low:
            return name, col
    base = (app_id or 'PLAYER').split('!')[0].split('_')[0]
    base = re.sub(r'\.exe$', '', base, flags=re.I)
    name = (base.split('.')[-1] or base or 'PLAYER')[:18]
    name = name[:1].upper() + name[1:]
    return name, QColor.fromHsl(sum(map(ord, name)) % 360, 150, 150).name()


class Media(QObject):
    """Опрашивает Windows GSMTC. Умеет: выбирать играющий плеер, помнить ручной выбор,
    игнорировать плееры, перематывать и отдавать список всех обнаруженных плееров."""
    updated = Signal(str, str, str, float, float, bool, object, int)
    playersChanged = Signal(str, list)      # (ключ активного, [{key,id,name,color,title,artist,playing}])

    def __init__(s):
        super().__init__()
        s.pinned = ''                 # ключ вручную выбранного плеера ('' = авто)
        s.auto = True
        s.ignored = []
        s.mgr = None
        s.cur = None                  # активная сессия GSMTC
        s.rows = []
        s.active_id = ''
        s.sessions_count = 0
        s.started = {}                # ключ → время начала воспроизведения (кто включился последним, тот и главный)
        s._errs = 0
        s.loop = asyncio.new_event_loop()
        threading.Thread(target=s.loop.run_forever, daemon=True).start()
        asyncio.run_coroutine_threadsafe(s.poll(), s.loop)

    def set_filters(s, auto: bool, ignore: str):
        s.auto = bool(auto)
        s.ignored = [x.strip().lower() for x in (ignore or '').split(',') if x.strip()]

    def set_player(s, key: str):
        s.pinned = key or ''

    def next_player(s):
        keys = [r['key'] for r in s.rows]
        if keys:
            i = keys.index(s.active_id) if s.active_id in keys else -1
            s.pinned = keys[(i + 1) % len(keys)]

    async def snapshot(s):
        if s.mgr is None:
            s.mgr = await wr('windows.media.control').GlobalSystemMediaTransportControlsSessionManager.request_async()
        sessions = list(s.mgr.get_sessions())
        cur = s.mgr.get_current_session()
        if not sessions and cur:           # как в v4: если список пуст, берём «текущую» сессию системы
            sessions = [cur]
        cur_id = (getattr(cur, 'source_app_user_model_id', '') or '') if cur else ''
        rows, seen = [], {}
        for x in sessions:
            try:
                app_id = getattr(x, 'source_app_user_model_id', '') or ''
                if any(ig in app_id.lower() for ig in s.ignored):
                    continue
                playing = x.get_playback_info().playback_status == 4
                info = await x.try_get_media_properties_async()
                name, col = player_info(app_id)
                n = seen[app_id] = seen.get(app_id, 0) + 1
                key = app_id if n == 1 else f"{app_id}#{n}"
                rows.append(dict(sess=x, key=key, id=app_id, name=name, color=col, playing=playing,
                                 title=info.title or '', artist=info.artist or '', info=info))
            except Exception:
                continue
        return rows, cur_id

    def choose(s, rows, cur_id):
        if not rows:
            return None
        now = time.time()
        for r in rows:
            if r['playing']:
                s.started.setdefault(r['key'], now)
            else:
                s.started.pop(r['key'], None)
        by_key = {r['key']: r for r in rows}
        if s.pinned in by_key:
            return by_key[s.pinned]
        if s.auto:
            pl = [r for r in rows if r['playing']]
            if pl:
                return max(pl, key=lambda r: (s.started.get(r['key'], 0), r['id'] == cur_id))
        if s.active_id in by_key:
            return by_key[s.active_id]
        for r in rows:
            if r['id'] == cur_id:
                return r
        return rows[0]

    async def cover(s, info):
        if not info.thumbnail:
            return b''
        st = await info.thumbnail.open_read_async()
        r = wr('windows.storage.streams').DataReader(st)
        await r.load_async(st.size)
        b = bytearray(st.size)
        r.read_bytes(b)
        return bytes(b)

    async def poll(s):
        last_key, last_sig, cov_empty, cov_tries = None, None, True, 0
        while True:
            try:
                rows, cur_id = await s.snapshot()
                s.rows = rows
                s.sessions_count = len(rows)
                x = s.choose(rows, cur_id)
                akey = x['key'] if x else ''
                sig = (tuple((r['key'], r['playing'], r['title']) for r in rows), akey)
                if sig != last_sig:
                    last_sig = sig
                    s.playersChanged.emit(akey, [{k: v for k, v in r.items() if k not in ('sess', 'info')} for r in rows])
                if x:
                    s.active_id, s.cur = akey, x['sess']
                    t = x['sess'].get_timeline_properties()
                    play = x['playing']
                    pos, dur = t.position.total_seconds(), t.end_time.total_seconds()
                    try:
                        if play:
                            pos += (datetime.now(timezone.utc) - t.last_updated_time).total_seconds()
                        pos = max(0., min(pos, dur or pos))
                    except Exception:
                        pass
                    key = (x['title'], x['artist'], akey)
                    need = key != last_key or (cov_empty and cov_tries < 4)   # обложка у браузеров часто приходит с задержкой
                    cov = None
                    if need:
                        cov_tries = 0 if key != last_key else cov_tries + 1
                        last_key = key
                        try:
                            cov = await s.cover(x['info'])
                        except Exception:
                            cov = b''
                        cov_empty = not cov
                    s.updated.emit(x['title'], x['artist'], x['name'], pos, dur, play, cov, len(rows))
                else:
                    s.cur, s.active_id, last_key = None, '', None
                    s.updated.emit('', '', '', 0., 0., False, b'', 0)
                s._errs = 0
            except Exception as ex:
                s._errs += 1
                if s._errs in (1, 20):
                    log(f"media poll: {ex!r}")
                s.mgr = None            # пересоздадим менеджер сессий при следующей попытке
            await asyncio.sleep(0.8)

    def cmd(s, name):
        async def run():
            try:
                if s.cur:
                    await getattr(s.cur, name)()
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(run(), s.loop)

    def seek(s, sec: float):
        async def run():
            try:
                if s.cur:
                    await s.cur.try_change_playback_position_async(int(max(sec, 0) * 10_000_000))
            except Exception:
                pass
        asyncio.run_coroutine_threadsafe(run(), s.loop)


class LyricsFetcher(QObject):
    loaded = Signal(str, list)

    def fetch(s, title, artist):
        key = f"{title}__{artist}"
        def run():
            try:
                q = urllib.parse.urlencode({'track_name': title, 'artist_name': artist})
                raw = safe_urlopen(f"https://lrclib.net/api/get?{q}", timeout=6)
                data = json.loads(raw.decode('utf-8'))
                lrc = data.get('syncedLyrics') or ''
                lines = []
                for row in lrc.splitlines():
                    m = re.match(r'\[(\d+):(\d+(?:\.\d+)?)\](.*)', row)
                    if m:
                        sec = int(m.group(1)) * 60 + float(m.group(2))
                        txt = m.group(3).strip()
                        if txt:
                            lines.append((sec, txt))
                s.loaded.emit(key, lines)
            except Exception:
                s.loaded.emit(key, [])
        threading.Thread(target=run, daemon=True).start()


class MediaMixin:
    """Часть класса Island: MediaMixin."""

    def on_media(s, t, a, app_name, pos, dur, play, cov, sess_cnt):
        was = s.playing
        s.playing = bool(t) and play
        s.mpos, s.mdur, s.mt0 = pos, dur, time.time()

        key = (t, a, app_name, play, sess_cnt)
        if key != s._mkey:            # тексты и иконки обновляем только при реальных изменениях
            s._mkey = key
            s.mtitle, s.martist, s.mapp = t, a, app_name
            s.update_src_btn()
            s.ttl.setText(s.ttl.fontMetrics().elidedText(t or 'Ничего не играет', Qt.ElideRight, 230))
            s.art.setText(a or ' ')
            s.pp.icon_name = 'pause' if play else 'play'
            s.pp.update()

        new_key = f"{t}__{a}"
        if t and new_key != s.lyrics_key and s.cfg.get('lyrics_enabled', True):
            s.lyrics_key = new_key
            s.lyrics = []
            s.cur_lyric = ''
            s.lrc_lab.setText('')
            s.lrc.fetch(t, a)

        if cov is not None:
            img = QImage.fromData(cov) if cov else QImage()
            if img.isNull():
                s.cov.clear()
                s.mini = None
                if s.cover_acc is not None:
                    s.cover_acc = None
                    s.refresh_accent()
                return
            c = img.scaled(1, 1, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).pixelColor(0, 0)
            h_, sa, _, _ = c.getHsl()
            s.cover_acc = QColor.fromHsl(max(h_, 0), max(sa, 140), 130)
            s.refresh_accent()            # применится, только если выбран режим «Акцент из обложки»
            pm = QPixmap.fromImage(img)
            s.cov.setPixmap(thumb(pm, 164).scaled(82, 82, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            s.mini = thumb(pm, 44).scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def on_players(s, active_key, rows):
        s.players = rows
        s.player_col = next((r['color'] for r in rows if r['key'] == active_key), None)
        s.update_src_btn()

    def update_src_btn(s):
        name = s.mapp or 'PLAYER'
        n = len(s.players)
        s.src_btn.setText(f"{name} ({n}) ▾" if n > 1 else f"{name} ▾")
        col = s.player_col or ('#141416' if STYLE['light'] else 'rgba(255,255,255,130)')
        ss = f'background:transparent;border:0;color:{col};font-size:10px;font-weight:700;padding:0'
        if s.src_btn.styleSheet() != ss:
            s.src_btn.setStyleSheet(ss)

    def show_players_menu(s):
        m = s.mk_menu(s)
        fg = '#141416' if STYLE['light'] else '#f2f2f5'
        fm = QFontMetrics(m.font())
        a = m.addAction(vicon('spark', fg, 18), 'Авто · последний играющий')
        a.setCheckable(True)
        a.setChecked(not s.media.pinned)
        a.triggered.connect(lambda _=False: s.media.set_player(''))
        m.addSeparator()
        if not s.players:
            m.addAction('Плееры не найдены').setEnabled(False)
        for r in s.players:
            txt = f"{r['name']} — {r['title']}" if r['title'] else r['name']
            act = m.addAction(dot_icon(r['color']), fm.elidedText(txt, Qt.ElideRight, 260) + ('   ▶' if r['playing'] else ''))
            act.setCheckable(True)
            act.setChecked(r['key'] == s.media.active_id)
            act.triggered.connect(lambda _=False, k=r['key']: s.media.set_player(k))
        m.exec(QCursor.pos())
        m.deleteLater()

    def on_seek(s, frac):
        if s.mdur > 0:
            sec = frac * s.mdur
            s.mpos, s.mt0 = sec, time.time()
            s.media.seek(sec)

    def on_lyrics(s, key, lines):
        if key == s.lyrics_key:
            s.lyrics = lines
