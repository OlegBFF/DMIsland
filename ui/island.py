"""Главное окно Island: сборка из миксинов, цикл анимации и отрисовка."""
import ctypes
import math
import time
from datetime import datetime
from PySide6.QtCore import (
    QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QTimer, QVariantAnimation, Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QLinearGradient, QPainter, QPen,
    QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QApplication, QPushButton, QStackedWidget, QVBoxLayout, QWidget
from core.config import PLACE_KEYS, STYLE_KEYS, WINDOW_KEYS, load_cfg, save_cfg
from core.clipstore import ClipStore
from core.constants import CH, DB_PATH, H, TH, TW, W
from core.db import open_database
from core.stores import ChatStore, ReminderStore, ShelfStore
from core.notif_rules import split_list
from core.utils import clamp, log
from core.win32 import WORKAREA, foreground_fullscreen, foreground_process_name, is_foreground_maximized_top, set_no_activate
from modules.apps import AppsMixin
from modules.assistant import AssistantMixin
from modules.assistant_cmds import AssistantCmdMixin
from modules.assistant_ctx import AssistantCtxMixin
from modules.audio import AudioMixin
from modules.capture import CaptureMixin
from modules.clipboard import ClipboardMixin
from modules.media import LyricsFetcher, Media, MediaMixin
from modules.notes import NotesMixin
from modules.notifications import DeviceWatcher, NotificationsMixin
from modules.recorder import RecorderMixin, ScreenRecorder
from modules.reminders import RemindersMixin
from modules.notify_center import NotifyMixin
from modules.shelf import ShelfMixin
from modules.spectrum import SpectrumAnalyzer
from modules.system_monitor import SystemMixin
from modules.text_tools import TextToolsMixin
from modules.weather import WeatherMixin
from core.mood import event_color, lerp_color, pick_mood
from ui.motion import Motion, scenario_for
from ui.animations import ANIM_STYLES, AnimationMixin, Sp
from ui.icons import VectorIcon
from ui.panels.chat import ChatPanel
from ui.panels.clip import ClipPanel
from ui.panels.home import HomePanel
from ui.panels.notes import NotesPanel
from ui.panels.shelf import ShelfPanel
from ui.panels.sys import SysPanel
from ui.panels.text import TextPanel
from ui.panels.weather import WeatherPanel
from ui.themes import STYLE, ThemeMixin, mix, qss, retint_inline
from ui.tray import TrayMixin
from ui.widgets import PillButton, TopBar, fnt
from ui.focus import FocusMixin
from ui.notif_card import CARD_W, PRIO_COL
from ui.panels.notifs import NotifsPanel
from ui.window import WindowMixin
from system.hub import SystemHub


class Island(
    ThemeMixin,
    AnimationMixin,
    TrayMixin,
    WindowMixin,
    HomePanel,
    ClipPanel,
    ShelfPanel,
    TextPanel,
    ChatPanel,
    NotesPanel,
    WeatherPanel,
    SysPanel,
    NotifsPanel,
    AppsMixin,
    ClipboardMixin,
    ShelfMixin,
    TextToolsMixin,
    AssistantMixin,
    AssistantCmdMixin,
    AssistantCtxMixin,
    NotesMixin,
    RemindersMixin,
    WeatherMixin,
    MediaMixin,
    AudioMixin,
    NotificationsMixin,
    SystemMixin,
    CaptureMixin,
    RecorderMixin,
    NotifyMixin,
    FocusMixin,
    QWidget
):
    weatherReady = Signal(dict)
    toastSignal = Signal(str, str, object, float)
    aiReplySignal = Signal(str)
    aiDeltaSignal = Signal(int, str)       # (номер запроса, фрагмент ответа)
    aiDoneSignal = Signal(int, str)        # (номер запроса, текст ошибки или '')
    clipTextSignal = Signal(str)           # текст в буфер обмена из рабочих потоков
    voiceSignal = Signal(str, str)         # ('text' | 'error', содержимое) — результат голосового ввода
    ctxOcrSignal = Signal(str, str, str)   # (подпись, текст, ошибка) — OCR для вложения чата
    notifImgSignal = Signal(int, object)   # (id уведомления, QImage) — картинка для превью в карточке

    def __init__(s):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        s.setAttribute(Qt.WA_TranslucentBackground)
        s.setAttribute(Qt.WA_ShowWithoutActivating)
        s.setAcceptDrops(True)

        s.cfg = load_cfg()
        s.update_theme_flag()
        s.cc = None
        s.db = open_database(DB_PATH)
        s.clips = ClipStore(s.db, **s.clip_opts())
        s.shelves, s.reminders, s.chats = ShelfStore(s.db), ReminderStore(s.db), ChatStore(s.db)
        legacy = s.cfg.pop('reminders', None)          # старые напоминания из config.json переезжают в базу
        if legacy:
            s.reminders.import_legacy(legacy)
            save_cfg(s.cfg)
        s.shelf = s.shelves.paths()
        s.init_assistant()
        s.init_ctx()
        s.hub = SystemHub()
        s.spectrum = SpectrumAnalyzer()
        s._spec_off_t, s._hub_flags, s._winmode_key = 0.0, (False, False), None
        s.app_hidden, s._hover_since, s.peek, s._act_t, s._fg_proc = False, 0.0, False, time.time(), ''
        s._notif_unread = {}
        s.init_notify()
        s.cover_acc = None                   # акцент, вытянутый из обложки трека
        s.fs, s.user_hidden = False, False   # полноэкранное окно / скрыт из трея
        s.priv = ('', '')                    # (кто слушает микрофон, кто использует камеру)
        s.players, s.player_col = [], None
        s._mkey = None
        s._fg_t, s._max_fg, s._fs_t = 0.0, False, 0.0
        s._acc_running = False
        s.toast_t0, s.toast_secs = 0.0, 1.0
        s.frame_ms_v = 16
        s._sub_menus = []
        s.eq = [Sp(3.0) for _ in range(4)]   # пружинные столбики эквалайзера
        s.mode = 'idle'
        s.big = False
        s.dodging = False
        s.last_tick = time.perf_counter()
        s.leave = 0.0
        s.until = 0.0
        s.toast = None

        s.sw, s.sh = Sp(236), Sp(CH)
        s.bx, s.bh = Sp(0), Sp(0)
        s._motion, s._last_mode, s._media_sig = Motion(), 'idle', (False, False)     # сценарии раскрытия (ui/motion.py)
        s.cont, s.stk, s.mood_k = Sp(0), Sp(0), Sp(0)                               # появление содержимого, стопка карточек, сила цвета
        s.mood_rgb, s.mood_name, s._panel_fx = (255.0, 255.0, 255.0), 'none', None
        s.bat = None
        s.acc = s.target_acc()
        STYLE['acc'] = QColor(s.acc)
        s.acc_anim = QVariantAnimation(s)
        s.acc_anim.setDuration(380)
        s.acc_anim.setEasingCurve(QEasingCurve.OutCubic)
        s.acc_anim.valueChanged.connect(s._acc_live)
        s.acc_anim.finished.connect(s._acc_done)
        s.mini = None
        s.playing = False
        s.mtitle, s.martist, s.mapp = '', '', 'PLAYER'
        s.mpos, s.mdur, s.mt0 = 0., 0., 0.
        s.lyrics_key = ''
        s.lyrics = []
        s.cur_lyric = ''

        s.mute = False
        s.tleft, s.ttotal, s.trun = 25 * 60, 25 * 60, False
        s.voice_listening = False
        s.weather_data = {'temp': None, 'desc': 'Ясно', 'hourly': [], 'daily': [], 'wind': 0, 'hum': 0, 'prcp': 0}

        s.media = Media()
        s.media.set_filters(s.cfg.get('player_auto', True), s.cfg.get('player_ignore', ''))
        s.devices = DeviceWatcher()
        s.lrc = LyricsFetcher()
        s.recorder = ScreenRecorder()

        s.setup_tray()
        s.build()
        s.update_notif_badges()

        s.media.updated.connect(s.on_media)
        s.media.playersChanged.connect(s.on_players)
        s.devices.event.connect(s.on_device_event)
        s.devices.privacy.connect(s.on_privacy)
        s.lrc.loaded.connect(s.on_lyrics)
        s.recorder.finished.connect(s.on_rec_finished)
        s.weatherReady.connect(s.on_weather_data)
        s.toastSignal.connect(s.pop)
        s.aiReplySignal.connect(s.on_ai_reply)
        s.aiDeltaSignal.connect(s.on_ai_delta)
        s.aiDoneSignal.connect(s.on_ai_done)
        s.clipTextSignal.connect(s.on_clip_text)
        s.voiceSignal.connect(s.on_voice)
        s.ctxOcrSignal.connect(s.on_ctx_ocr)
        s.hub.snapshot.connect(s.on_hub_snapshot)
        s.hub.notice.connect(s.on_hub_notice)
        QGuiApplication.clipboard().dataChanged.connect(s.clip_changed)

        s.apply_window_integration()
        s.place(False)
        s.show()
        s.init_focus()
        s.slow()
        s.fetch_weather()
        s.hub.set_active(True, False)
        s.hub.refresh()                                 # реальная громкость и устройства сразу после запуска

        # Адаптивный таймер: интервал = частота монитора при активности, 220 мс в покое
        s.frame_ms_v = s.frame_ms()
        s.anim_timer = QTimer(s)
        s.anim_timer.setTimerType(Qt.PreciseTimer)
        s.anim_timer.timeout.connect(s.tick)
        s.anim_timer.start(s.frame_ms_v)

        for ms, fn in ((5000, s.slow), (1000, s.second), (900000, s.fetch_weather)):
            t = QTimer(s)
            t.timeout.connect(fn)
            t.start(ms)

        QApplication.instance().aboutToQuit.connect(s.shutdown)

    def _notif_unread_important(s) -> bool:
        return bool(s._notif_unread.get('important'))

    def shutdown(s):
        """Выход: сначала возвращаем рабочую область Windows, затем останавливаем потоки и закрываем базу."""
        for step in (WORKAREA.restore, s.listener.stop, s.spectrum.stop, s.hub.stop, s.recorder.shutdown, s.db.close):
            try:
                step()
            except Exception as ex:
                log(f"shutdown {getattr(step, '__name__', step)}: {ex!r}")

    def on_hub_snapshot(s, res):
        if 'audio' in res:
            s.apply_audio_snapshot(res['audio'])
        if 'winmode' in res:
            key = tuple(sorted(res['winmode'].items()))
            if key != s._winmode_key:
                first, s._winmode_key = s._winmode_key is None, key
                if not first and s.cfg.get('theme') == 'system':
                    s.sync_win_theme()                  # режим Windows сменили (в том числе из панели) — остров следует за ним
        if s.cc is not None:
            s.cc.apply(s.hub.state, res.keys())

    def on_hub_notice(s, title, text, ok):
        if s.mode == 'open' and s.cc is not None:
            s.cc.flash(f"{title}: {text}")              # тост свернул бы остров, пока с ним работают
        else:
            ev = event_color(title, ok)                      # Bluetooth — голубой, таймер — оранжевый, ошибка — красный
            col = QColor(*ev) if ev else (QColor('#34c759') if ok else QColor('#ff453a'))
            s.pop(title, text, (col, 'check' if ok else 'close'), 3.2 if ok else 4.5)

    def sync_background(s, vis, now):
        """Фоновые потоки работают только когда нужны: опрос системы — на открытой вкладке, анализ звука — пока играет музыка."""
        flags = (bool(vis), bool(vis and s.stack.currentIndex() == 7))
        if flags != s._hub_flags:
            s._hub_flags = flags
            s.hub.set_active(*flags)
        if s.playing and not s.fs:
            s._spec_off_t = 0.0
            if not s.spectrum.running or s.spectrum._stop.is_set():
                s.spectrum.start()
        elif s.spectrum.running:
            s._spec_off_t = s._spec_off_t or now
            if now - s._spec_off_t > 3.0:
                s.spectrum.stop()
                s._spec_off_t = 0.0

    def build(s):
        s.panel = QWidget(s)
        s.inner = QWidget(s.panel)
        s.inner.setFixedSize(W - 36, H - 32)
        s.inner.setStyleSheet(qss(s.acc, STYLE['light']))

        root = QVBoxLayout(s.inner)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        s.tabs = TopBar([
            ('home', 'Главная'),
            ('clip', 'Буфер'),
            ('shelf', 'Полка'),
            ('text', 'Текст'),
            ('chat', 'Чат'),
            ('notes', 'Заметка'),
            ('weather', 'Погода'),
            ('sys', 'Управление'),
            ('bell', 'Уведомления'),
        ])
        root.addWidget(s.tabs)

        s.stack, s.anims = QStackedWidget(), []
        root.addWidget(s.stack, 1)

        pages = (s.pg_home, s.pg_clip, s.pg_shelf, s.pg_text, s.pg_chat, s.pg_notes, s.pg_weather, s.pg_sys, s.pg_notifs)
        for f in pages:
            w = f()
            a = QPropertyAnimation(w, b'pos', w)
            a.setDuration(220)
            a.setStartValue(QPoint(24, 0))
            a.setEndValue(QPoint(0, 0))
            a.setEasingCurve(QEasingCurve.OutCubic)
            s.anims.append(a)
            s.stack.addWidget(w)

        s.tabs.changed.connect(s.switch)
        s.tabs.actionTriggered.connect(s.on_top_action)
        s.bar.seeked.connect(s.on_seek)
        s.pp.badge_col = QColor(s.acc)
        retint_inline(s.inner, STYLE['light'])

    def switch(s, i):
        d = 1 if i >= s.stack.currentIndex() else -1      # страница въезжает со стороны, куда ушли
        s.stack.setCurrentIndex(i)
        a = s.anims[i]
        a.stop()
        a.setStartValue(QPoint(28 * d, 0))
        a.setEasingCurve(QEasingCurve.OutQuint)
        a.setDuration(300)
        a.start()

    def on_top_action(s, act):
        if act == 'voice':
            s.toggle_voice()
        elif act == 'settings':
            s.open_settings()

    def btn(s, text, fn=None):
        b = PillButton(text)
        if fn:
            b.clicked.connect(fn)
        return b

    def apply_settings(s, style=True, window=True, place=False):
        if style:
            s.update_theme_flag()
            s.refresh_accent()
            s.restyle()
        s.apply_clip_options()
        if s.cfg.get('notif_enabled', True):
            s.listener.start()                          # идемпотентно
        s.media.set_filters(s.cfg.get('player_auto', True), s.cfg.get('player_ignore', ''))
        if window:
            s.apply_window_integration()
        elif place:
            s.place(s.big)
        s.frame_ms_v = s.frame_ms()
        s.sync_visibility()
        s.update()

    def set_cfg(s, key, val):
        s.cfg[key] = val
        save_cfg(s.cfg)
        s.apply_settings(style=key in STYLE_KEYS, window=key in WINDOW_KEYS, place=key in PLACE_KEYS)

    def toggle_cfg(s, key, default=False):
        s.set_cfg(key, not s.cfg.get(key, default))

    def toggle_open(s):
        if s.user_hidden:
            s.user_hidden = False
            s.sync_visibility()
        if s.mode == 'open' and s.tabs.pinned:
            s.tabs.pinned, s.mode = False, 'idle'
        else:
            s.tabs.pinned, s.mode, s.leave = True, 'open', 0
        s.tabs.update()

    def frame_ms(s) -> int:
        """Интервал анимации = частота монитора (60 Гц → 16 мс, 144 Гц → 7 мс). Без лишних кадров."""
        try:
            hz = s.get_target_screen().refreshRate()
        except Exception:
            hz = 60.0
        return int(clamp(round(1000.0 / max(hz, 30.0)), 6, 17))

    def dragEnterEvent(s, e):
        if e.mimeData().hasUrls():
            s.mode = 'open'
            s.switch(2)
            e.acceptProposedAction()

    def dropEvent(s, e):
        s.shelf_add([u.toLocalFile() for u in e.mimeData().urls() if u.toLocalFile()])
        s.pop('Полка', f'Файлов на полке: {len(s.shelf)}', (QColor('#0a84ff'), 'shelf'))

    def mousePressEvent(s, e):
        if s.mode == 'idle' and s.recorder.recording:
            s.recorder.stop()
            return
        if s.mode == 'toast':
            s.mode = 'idle'
            return
        super().mousePressEvent(e)

    def set_panel_fade(s, c):
        """Прозрачность панели (QGraphicsOpacityEffect включается только на время перехода — в покое он не нужен)."""
        if s._panel_fx is None:
            s._panel_fx = QGraphicsOpacityEffect(s.panel)
            s.panel.setGraphicsEffect(s._panel_fx)
        if c < 0.985:
            s._panel_fx.setEnabled(True)
            s._panel_fx.setOpacity(c)
        elif s._panel_fx.isEnabled():
            s._panel_fx.setEnabled(False)

    def update_mood(s, now, dt):
        st = {'recording': s.recorder.recording, 'timer': s.trun, 'playing': s.playing,
              'unread_important': s._notif_unread_important()}
        cv = QColor(s.cover_acc) if getattr(s, 'cover_acc', None) is not None else QColor(s.acc)
        st['cover'] = (cv.red(), cv.green(), cv.blue())
        if s.mode == 'notif' and 0 <= s.ncur < len(s.nq):
            st['card_prio'] = s.nq[s.ncur].get('priority')
        elif s.mode == 'toast' and s.toast:
            t, _, ic = s.toast
            col = ic[0] if isinstance(ic, tuple) else (ic if isinstance(ic, QColor) else None)
            ev = event_color(t)
            if ev is not None:
                st['toast_col'] = ev
            elif col is not None:
                st['toast_col'] = (QColor(col).red(), QColor(col).green(), QColor(col).blue())
        name, rgb, strength = pick_mood(st) if s.cfg.get('adaptive_color', True) else ('none', None, 0.0)
        if rgb is not None:
            s.mood_rgb = lerp_color(s.mood_rgb, rgb, dt, 7.0)
        s.mood_name = name
        s.mood_k.tgt = strength
        s.mood_k.step(.14, .72, dt)

    def mood_color(s) -> QColor:
        r, g, b = s.mood_rgb
        return QColor(int(r), int(g), int(b))

    def tick(s):
        now_perf = time.perf_counter()
        dt = clamp(now_perf - s.last_tick, 0.004, 0.05)
        s.last_tick = now_perf

        # Игровой режим: прячем остров, пока в фокусе окно на весь монитор (игра, видео, презентация)
        if now_perf - s._fs_t > 0.4:
            s._fs_t = now_perf
            fs = s.cfg.get('game_mode', 'hide') == 'hide' and foreground_fullscreen(int(s.winId()))
            hide_list = split_list(s.cfg.get('hide_apps', ''))
            s._fg_proc = foreground_process_name() if hide_list else ''
            ah = bool(s._fg_proc and any(h in s._fg_proc for h in hide_list))     # для этих программ остров прячется (плеер, игра, презентация)
            if fs != s.fs or ah != s.app_hidden:
                s.fs, s.app_hidden = fs, ah
                s.sync_visibility()
                if not (fs or ah):
                    QTimer.singleShot(600, s.flush_backlog)                      # сводка о том, что пришло, пока вы были заняты
        if not s.isVisible():
            if s.spectrum.running:
                s.spectrum.stop()
            if s.anim_timer.interval() != 250:
                s.anim_timer.setInterval(250)
            return

        now, p = time.time(), QCursor.pos()
        lx, ly, cx = p.x() - s.x(), p.y() - s.y(), s.width() / 2
        w, h = s.sw.x, s.sh.x
        inx = abs(lx - cx) < max(w, 260 if s.peek else 0) / 2 + 10

        fit = s.cfg.get('window_fit', 'smart_dodge')
        alt_held = bool(ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000)
        if now_perf - s._fg_t > 0.12:           # Win32-проверка окна не чаще ~8 раз в секунду
            s._fg_t, s._max_fg = now_perf, is_foreground_maximized_top()
        max_fg = s._max_fg

        # Умный обход вкладок браузера (smart_dodge): над вкладками остров сжимается и пропускает клики,
        # раскрывается у самой верхней грани экрана (0..4 px) или с зажатым Alt.
        if fit == 'smart_dodge' and max_fg and s.mode == 'idle' and not s.recorder.recording:
            if inx and 5 <= ly <= 44 and not alt_held:
                if not s.dodging:
                    s.dodging = True
                    s.set_transparent_input(True)
            else:
                if s.dodging:
                    s.dodging = False
                    s.set_transparent_input(bool(s.cfg.get('click_through')))
        elif s.dodging:
            s.dodging = False
            s.set_transparent_input(bool(s.cfg.get('click_through')))

        if s.mode == 'notif':
            s.tick_notif(now, inx, ly, h)
        elif not s.cfg.get('click_through') and not s.dodging:
            trigger_h = 4 if (fit == 'smart_dodge' and max_fg) else (h + 4)
            if s.mode != 'open':
                if inx and 0 <= ly <= trigger_h:
                    # Защита от случайных касаний: остров раскрывается, когда курсор задержался у грани (Alt — мгновенно)
                    s._hover_since = s._hover_since or now
                    if now - s._hover_since >= (0.0 if alt_held else float(s.cfg.get('open_delay', 0.12))):
                        s.mode, s.leave, s._hover_since = 'open', 0, 0.0
                else:
                    s._hover_since = 0.0
                    if s.mode == 'toast' and now > s.until:
                        s.mode = 'idle'
            elif s.tabs.pinned or s._typing or s.chat_hold() or (inx and ly < h + 14):
                s.leave = 0
            elif not s.leave:
                s.leave = now
            elif now - s.leave > .36:
                s.mode, s.leave = 'idle', 0
        elif s.mode == 'toast' and now > s.until:
            s.mode = 'idle'

        if s.mode != 'idle' or (inx and ly < 90) or s.recorder.recording or s.playing or s.nq or s._typing:
            s._act_t = now                                   # любая активность возвращает остров из «подглядывания»
        s.peek = bool(s.cfg.get('auto_peek', True) and max_fg and fit in ('smart_dodge', 'titlebar_snap') and s.mode == 'idle'
                      and not s.dodging and not s._notif_unread_important() and now - s._act_t > float(s.cfg.get('peek_after', 4.0)))
        pmode = s.cfg.get('pill_music', 'normal')
        idle_w, idle_h = 236, (14 if s.dodging else CH)
        if s.peek:
            idle_w, idle_h = 96, 7
        if s.recorder.recording:
            idle_w = 270
        elif s.playing and not s.dodging:
            if pmode == 'wide':
                idle_w = 340
            elif pmode == 'mini':
                idle_w, idle_h = 360, 52
            else:
                idle_w = 310

        targets = {'idle': (idle_w, idle_h), 'open': (W, H), 'toast': (TW, TH), 'notif': (CARD_W, s.notif_h())}
        tw, th_ = targets[s.mode]
        sig = (s.playing, s.recorder.recording)
        if s.mode != s._last_mode:                         # у каждого вида раскрытия свой характер движения
            s._motion.start(scenario_for(s._last_mode, s.mode), now_perf)
            s._last_mode = s.mode
        elif sig != s._media_sig and s.mode == 'idle':     # музыка/запись меняют ширину «таблетки» — мягко и медленно
            s._motion.start('media', now_perf)
        s._media_sig = sig
        k, dmp = ANIM_STYLES.get(s.cfg.get('anim_style', 'liquid'), ANIM_STYLES['liquid'])[:2]
        if s.cfg.get('motion_scenarios', True):
            kw, dw, kh, dh, w_go, h_go = s._motion.params(now_perf, k, dmp)
        else:
            kw, dw, kh, dh, w_go, h_go = k, dmp, k, dmp, True, True
        if w_go:
            s.sw.tgt = tw
        if h_go:
            s.sh.tgt = th_
        s.sw.step(kw, dw, dt)
        s.sh.step(kh, dh, dt)

        # цвет «настроения»: музыка → обложка, запись → красный, таймер → оранжевый, событие/важное уведомление → свой сигнал
        s.update_mood(now, dt)

        # стопка карточек: при нескольких уведомлениях позади капсулы «складываются» ещё одна-две
        s.stk.tgt = float(min(len(s.nq) - 1, 2)) if (s.mode == 'notif' and len(s.nq) > 1) else 0.0
        s.stk.step(.2, .62, dt)

        big = s.mode != 'idle' or s.sw.x > 460 or s.sh.x > CH + 24
        if big != s.big:
            s.big = big
            s.place(big)
            s.set_transparent_input(bool(s.cfg.get('click_through') and not big))

        vis = s.sh.x > 90 and s.mode not in ('toast', 'notif')
        s.sync_background(vis, now_perf)
        # содержимое проявляется с небольшим подъёмом, когда капсула почти раскрылась, и гаснет раньше, чем она свернётся
        want = 1.0 if (s.mode == 'open' and s.sh.x > 0.5 * H) else 0.0
        s.cont.tgt = want
        s.cont.step(.2 if want else .4, .72 if want else .5, dt)
        c_ = clamp(s.cont.x)
        s.panel.setVisible(vis or c_ > 0.02)
        s.set_panel_fade(c_)
        cw_, ch_ = clamp(s.sw.x - 36, 0, W - 36), max(s.sh.x - 32, 0)
        s.panel.setGeometry(int(cx - cw_ / 2), 14, int(cw_), int(ch_))
        s.inner.move(-int((W - 36 - cw_) / 2), int((1.0 - c_) * 12))
        s.sync_card(cx)

        if vis:
            s.tabs.update()
            s.vol.update()
        if s.playing:
            pos = min(s.mpos + (now - s.mt0), s.mdur or 9999)
            if vis:
                s.bar.setMaximum(max(int(s.mdur * 10), 1))
                s.bar.setValue(int(pos * 10))
                rem = max(0, int(s.mdur - pos))
                s.tl_el.setText(f"{int(pos) // 60}:{int(pos) % 60:02d}")
                s.tl_rem.setText(f"-{rem // 60}:{rem % 60:02d}")
            if s.lyrics and s.cfg.get('lyrics_enabled', True):
                cur = ''
                for sec, ltxt in s.lyrics:
                    if sec <= pos:
                        cur = ltxt
                    else:
                        break
                if cur != s.cur_lyric:
                    s.cur_lyric = cur
                    s.lrc_lab.setText(s.lrc_lab.fontMetrics().elidedText(cur, Qt.ElideRight, 260))

        # Пружинный эквалайзер в пилюле: бары плавно оседают при паузе
        lv = s.spectrum.levels                          # реальный спектр системного звука (4 полосы), а не синусоиды
        live = s.playing and s.spectrum.running
        for i, sp in enumerate(s.eq):
            sp.tgt = (3.0 + 11.0 * lv[i]) if live else 3.0
            sp.step(.32, .55, dt)

        dy = ly - h
        near = (s.mode == 'idle' and not s.dodging and not s.cfg.get('click_through') and 0 < dy < 72 and abs(lx - cx) < w / 2 + 80)
        s.bh.tgt = 18 * (72 - dy) / 72 if near else 0.0
        if near:
            s.bx.tgt = clamp(lx - cx, -w / 2 + 36, w / 2 - 36)
        s.bh.step(.25, .64, dt)
        s.bx.step(.28, .64, dt)

        # Адаптивное энергосбережение: если всё неподвижно и курсор далеко — кадр раз в 220 мс
        active = (s.mode != 'idle' or s.playing or s.recorder.recording or near or s.dodging or s._acc_running
                  or not s.sw.settled() or not s.sh.settled() or not s.bh.settled()
                  or not s.cont.settled(.01) or not s.stk.settled(.01) or not s.mood_k.settled(.01) or s.mood_name in ('important', 'recording')
                  or any(not sp.settled(.15) for sp in s.eq)
                  or bool(s.priv[0] or s.priv[1])
                  or s.cfg.get('character', 'none') != 'none')
        want_iv = s.frame_ms_v if active else 220
        if s.anim_timer.interval() != want_iv:
            s.anim_timer.setInterval(want_iv)

        s.update()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        now, cx = time.time(), s.width() / 2
        w, h = s.sw.x, max(s.sh.x, 12)
        th = STYLE['th']

        op = 0.45 if s.dodging else (0.62 if s.peek else (s.cfg.get('opacity_open', 0.98) if s.mode == 'open' else s.cfg.get('opacity_idle', 0.96)))
        p.setOpacity(op)

        mk, mc = s.mood_k.x, s.mood_color()
        pulse = 0.5 + 0.5 * math.sin(now * 3.4) if s.mood_name in ('important', 'recording') else 0.5

        # Мягкое свечение: цвет «настроения» (обложка / красный / оранжевый / голубой…) или, у неоновых тем, акцент
        glow_col, glow_a = None, 0
        if mk > 0.03 and not s.dodging:
            glow_col, glow_a = mc, int((26 + 52 * mk) * (0.8 + 0.4 * pulse))
        elif (th.get('glow') and s.cfg.get('glow', True) and not s.dodging
                and (s.playing or s.mode != 'idle' or s._acc_running)):
            glow_col, glow_a = QColor(s.acc), (int(48 + 20 * math.sin(now * 2.2)) if s.playing else 54)
        if glow_col is not None:
            rad = max(min(w * 0.68, s.width() / 2 - 2), 40)
            ky = clamp((s.height() - h * 0.5 - 2) / rad, 0.15, 0.45)
            c0, c1 = QColor(glow_col), QColor(glow_col)
            c0.setAlpha(min(glow_a, 255))
            c1.setAlpha(0)
            gl = QRadialGradient(QPointF(0, 0), rad)
            gl.setColorAt(0, c0)
            gl.setColorAt(1, c1)
            p.save()
            p.translate(cx, h * 0.5)
            p.scale(1.0, ky)
            p.fillRect(QRectF(-rad, -rad, rad * 2, rad * 2), gl)
            p.restore()

        if not s.dodging:
            for g in (9, 5):
                p.fillPath(s.liquid_path(cx, w, h, g, now), QColor(0, 0, 0, 20))

        # стопка: позади капсулы выглядывают следующие карточки очереди (складываются плавно, цвет — приоритет сообщения)
        if s.stk.x > 0.02 and not s.dodging:
            others = [x for j, x in enumerate(s.nq) if j != s.ncur]
            for i in (2, 1):
                f = clamp(s.stk.x - (i - 1))
                if f <= 0.01 or i > len(others):
                    continue
                pc = QColor(PRIO_COL.get(others[i - 1].get('priority'), PRIO_COL['normal']))
                body = mix(QColor(th['base2']), pc, .26)
                body.setAlpha(int(255 * (0.95 - 0.18 * i) * f))
                p.save()
                p.translate(0, 9.0 * i * f)
                gp = s.liquid_path(cx, w * (1 - 0.06 * i), h, 0.001, now)
                p.fillPath(gp, body)
                edge_c = QColor(pc)
                edge_c.setAlpha(int(170 * f))
                p.setPen(QPen(edge_c, 1.0))
                p.drawPath(gp)
                p.restore()

        path = s.liquid_path(cx, w, h, 0, now)
        base_col, base2 = QColor(th['base']), QColor(th['base2'])
        gr = QLinearGradient(0, 0, 0, h)
        gr.setColorAt(0, base_col)
        if mk > 0.03:
            gr.setColorAt(1, mix(base2, mc, .10 + .24 * mk))
        else:
            gr.setColorAt(1, mix(base2, s.acc, .15) if (s.playing or s.mode == 'open') else base2)
        p.fillPath(path, gr)

        edge = QColor(0, 0, 0, th['border']) if STYLE['light'] else QColor(255, 255, 255, th['border'])
        if mk > 0.03:
            border_col = mix(edge, mc, min(1.0, .35 + .6 * mk * (0.75 + 0.25 * pulse)))
        else:
            border_col = s.acc if (s.playing and s.cfg.get('edge_eq', True)) else edge
        p.setPen(QPen(border_col, 1.25))
        p.drawPath(path)

        if s.mode == 'notif':
            s.paint_notif_ring(p, cx, w, h, now)           # обводка цветом приоритета (у важных пульсирует)
        if s.dodging or s.peek:
            return

        x0 = cx - w / 2
        fg = QColor('#141416') if STYLE['light'] else QColor('white')

        if s.mode == 'idle':
            p.setOpacity(op * clamp(1 - (h - CH) / 24))
            s.paint_notif_badge(p, x0, w, h, now)
            if s.recorder.recording:
                el = int(now - s.recorder.start_t)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor('#ff453a'))
                p.drawEllipse(QPointF(x0 + 22, h / 2), 5 + 1.2 * math.sin(now * 5), 5 + 1.2 * math.sin(now * 5))
                p.setPen(fg)
                p.setFont(fnt(10.5, QFont.DemiBold))
                p.drawText(QRectF(x0 + 34, 0, 70, h), Qt.AlignVCenter | Qt.AlignLeft, f"{el // 60}:{el % 60:02d}")
                p.setPen(QColor('#ff6961'))
                p.drawText(QRectF(x0 + w - 68, 0, 56, h), Qt.AlignCenter, '■ Стоп')
                return

            ch = s.cfg.get('character', 'none')
            if s.playing and s.mini:
                p.drawPixmap(int(x0 + 14), int((h - 22) / 2), s.mini)
            elif ch != 'none':
                s.draw_character(p, x0 + 28, h / 2, ch, now)
            else:
                VectorIcon.draw(p, 'sun', QRectF(x0 + 14, (h - 20) / 2, 20, 20))

            parts = [datetime.now().strftime('%H:%M')]
            if s.shelf:
                parts.insert(0, f"[{len(s.shelf)}]")
            if s.trun:
                parts.append(f"{s.tleft // 60:02d}:{s.tleft % 60:02d}")
            if s.weather_data['temp'] is not None:
                parts.append(f"{s.weather_data['temp']}°")

            p.setPen(fg)
            p.setFont(fnt(10.5, QFont.DemiBold))
            if s.playing and s.cfg.get('pill_music') in ('wide', 'mini') and (s.cur_lyric or s.mtitle):
                show_t = s.cur_lyric or f"{s.mtitle} — {s.martist}"
                p.drawText(QRectF(x0 + 44, 0, w - 92, h), Qt.AlignCenter,
                           QFontMetrics(p.font()).elidedText(show_t, Qt.ElideRight, int(w - 96)))
            else:
                p.drawText(QRectF(x0, 0, w, h), Qt.AlignCenter, '   '.join(parts))

            # Эквалайзер на пружинах (плавно «оседает» при паузе)
            eq_on = s.eq[0].x > 3.4 or s.playing
            if eq_on:
                p.setPen(Qt.NoPen)
                p.setBrush(mc if s.mood_name == 'music' else s.acc)
                for i, sp in enumerate(s.eq):
                    bh_bar = max(sp.x, 2.5)
                    p.drawRoundedRect(QRectF(x0 + w - 34 + i * 5, (h - bh_bar) / 2, 3, bh_bar), 1.5, 1.5)

            # Индикаторы приватности (как у iOS): оранжевая точка — микрофон, зелёная — камера
            if s.cfg.get('privacy_dots', True) and (s.priv[0] or s.priv[1]):
                bx = x0 + w - (48 if eq_on else 20)
                p.setPen(Qt.NoPen)
                pulse = 0.35 * math.sin(now * 4.0)
                for i, (on, col) in enumerate(((s.priv[0], '#ff9f0a'), (s.priv[1], '#30d158'))):
                    if on:
                        p.setBrush(QColor(col))
                        rr = 3.4 + pulse
                        p.drawEllipse(QPointF(bx, h / 2), rr, rr)
                        bx -= 11

        elif s.mode == 'toast' and s.toast:
            t, sub, ic = s.toast
            age = now - s.toast_t0
            p.setOpacity(op * clamp((w - 260) / 100))
            r = QRectF(x0 + 16, h / 2 - 24, 48, 48)
            accent = s.acc
            # Пружинный «поп» иконки + въезд текста
            pop = 1.0 + 0.30 * math.exp(-age * 6.5) * math.cos(age * 16.0)
            slide = 16.0 * math.exp(-age * 7.0)
            p.save()
            p.translate(r.center())
            p.scale(pop, pop)
            p.translate(-r.center().x(), -r.center().y())
            if isinstance(ic, (QColor, tuple)):
                col, ic_name = ic if isinstance(ic, tuple) else (ic, 'sun')
                accent = QColor(col)
                VectorIcon.draw(p, ic_name, r, QColor('white'), col)
            elif isinstance(ic, QPixmap) and not ic.isNull():
                p.drawPixmap(r.toRect(), ic)
            p.restore()

            fade = clamp(age * 5.0)
            p.setOpacity(p.opacity() * fade)
            p.setPen(fg)
            p.setFont(fnt(11.5, QFont.DemiBold))
            p.drawText(QRectF(x0 + 76 + slide, h / 2 - 24, w - 92, 24), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(p.font()).elidedText(t, Qt.ElideRight, int(max(w - 100, 40))))
            p.setPen(QColor(255, 255, 255, 155) if not STYLE['light'] else QColor(20, 20, 22, 160))
            p.setFont(fnt(9.5))
            p.drawText(QRectF(x0 + 76 + slide * 1.4, h / 2, w - 92, 22), Qt.AlignVCenter | Qt.AlignLeft, sub)

            if t.startswith('#'):
                for idx, hex_c in enumerate(s.cfg.get('color_history', [])[:4]):
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(hex_c))
                    p.drawEllipse(QPointF(x0 + w - 76 + idx * 16, h / 2 + 10), 5.5, 5.5)

            # Тонкая полоска оставшегося времени уведомления
            if w > 380:
                frac = clamp((s.until - now) / max(s.toast_secs, 0.5))
                p.setOpacity(op * 0.8)
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawRoundedRect(QRectF(x0 + 22, h - 8, (w - 44) * frac, 2.4), 1.2, 1.2)
