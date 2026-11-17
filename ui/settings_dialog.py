"""Окно настроек."""
import copy
import ctypes
import html
import os
import time
from pathlib import Path
from PySide6.QtCore import QSize, QTimer, Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)
from system.util import open_settings
from core.config import DEFAULT_CFG, PLACE_KEYS, STYLE_KEYS, WINDOW_KEYS, save_cfg
from core.constants import APP_NAME, APP_VER, CFG_PATH, LOG_PATH, SHOTS_DIR
from core.security import dpapi_decrypt, dpapi_encrypt
from core.win32 import autostart_enabled, set_autostart
from ui.animations import ANIM_STYLES
from ui.icons import vicon
from ui.themes import ACCENT_PRESETS, FD, FF, STYLE, THEMES, mix, on_acc, rgba
from ui.widgets import Segmented, Slider, ThemeCard, Toggle


class SettingsDialog(QDialog):
    """Окно настроек: боковая навигация, живой предпросмотр (тема, акцент, размер — сразу на острове),
    «Отмена» откатывает всё к исходному состоянию, «Сохранить» пишет конфиг и шифрует ключи (DPAPI)."""

    def __init__(s, isl):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        s.isl, s.cfg = isl, isl.cfg
        s.orig = copy.deepcopy(isl.cfg)
        s.saved = False
        s.cfg['autostart'] = autostart_enabled()
        s.setWindowTitle(f'{APP_NAME} — Настройки')
        s.setWindowIcon(isl.make_tray_icon())
        s.resize(860, 640)
        s.setMinimumSize(780, 540)

        root = QHBoxLayout(s)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QFrame()
        side.setObjectName('side')
        side.setFixedWidth(200)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 20, 0, 12)
        sv.setSpacing(2)
        ttl = QLabel(APP_NAME)
        ttl.setObjectName('h1')
        ttl.setContentsMargins(20, 0, 0, 0)
        ver = QLabel(f'версия {APP_VER}')
        ver.setObjectName('hint')
        ver.setContentsMargins(20, 0, 0, 10)
        sv.addWidget(ttl)
        sv.addWidget(ver)
        s.nav = QListWidget()
        s.nav.setObjectName('nav')
        s.nav.setIconSize(QSize(20, 20))
        s.nav.setFocusPolicy(Qt.NoFocus)
        sv.addWidget(s.nav, 1)
        root.addWidget(side)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        s.stack = QStackedWidget()
        right.addWidget(s.stack, 1)
        foot = QFrame()
        foot.setObjectName('foot')
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(24, 12, 24, 12)
        fh.addStretch()
        b_cancel = QPushButton('Отмена')
        b_cancel.clicked.connect(s.reject)
        b_save = QPushButton('Сохранить')
        b_save.setObjectName('primary')
        b_save.clicked.connect(s.save)
        fh.addWidget(b_cancel)
        fh.addWidget(b_save)
        right.addWidget(foot)
        root.addLayout(right, 1)

        s.pages = [('gear', 'Основные', s._pg_general), ('palette', 'Оформление', s._pg_look),
                   ('music', 'Музыка', s._pg_music), ('game', 'Игры и устройства', s._pg_devices),
                   ('chat', 'ИИ и ссылки', s._pg_ai), ('bell', 'Уведомления', s._pg_notif), ('info', 'О программе', s._pg_about)]
        for _, name, fn in s.pages:
            s.nav.addItem(QListWidgetItem(name))
            fn()
        s.nav.currentRowChanged.connect(s.stack.setCurrentIndex)
        s.nav.setCurrentRow(0)
        s.restyle()

        s._tm = QTimer(s)
        s._tm.timeout.connect(s._refresh_players)
        s._tm.start(1000)

    # ---------- стиль ----------
    def sheet(s):
        th, lt, acc = STYLE['th'], STYLE['light'], STYLE['acc']
        bg = '#f6f6f9' if lt else mix(QColor(th['card_end']), QColor('#1b1b20'), .35).name()
        side = '#ebebf1' if lt else mix(QColor(th['base']), QColor('#101014'), .5).name()
        fg = '#141416' if lt else '#f2f2f5'
        sub = 'rgba(20,20,22,140)' if lt else 'rgba(255,255,255,125)'
        e = '0,0,0' if lt else '255,255,255'
        inp = f'rgba({e},{9 if lt else 12})'
        hov = f'rgba({e},{16 if lt else 20})'
        line = f'rgba({e},{16 if lt else 14})'
        return f"""
        QDialog {{ background: {bg}; }}
        * {{ color: {fg}; font-family: {FF}; font-size: 13px; }}
        QLabel {{ background: transparent; }}
        #side {{ background: {side}; border-right: 1px solid {line}; }}
        #foot {{ background: {side}; border-top: 1px solid {line}; }}
        #h1 {{ font-family: {FD}; font-size: 18px; font-weight: 700; }}
        #hint {{ color: {sub}; font-size: 11.5px; }}
        #sec_t {{ color: {sub}; font-size: 11.5px; font-weight: 700; padding: 4px 4px 0 4px; }}
        #sec {{ background: rgba({e},{6 if lt else 7}); border: 1px solid {line}; border-radius: 14px; }}
        #nav {{ background: transparent; border: 0; outline: 0; }}
        #nav::item {{ padding: 10px 12px; border-radius: 10px; margin: 2px 10px; }}
        #nav::item:hover {{ background: {hov}; }}
        #nav::item:selected, #nav::item:selected:!active {{ background: {rgba(acc, 64)}; color: {fg}; }}
        QLineEdit, QComboBox {{ background: {inp}; border: 1px solid {line}; border-radius: 9px;
                               padding: 6px 10px; min-height: 18px; selection-background-color: {rgba(acc, 120)}; }}
        QLineEdit:focus, QComboBox:focus {{ border: 1px solid {acc.name()}; }}
        QComboBox::drop-down {{ border: 0; width: 22px; }}
        QComboBox QAbstractItemView {{ background: {bg}; border: 1px solid {line}; outline: 0; padding: 4px;
                                       selection-background-color: {rgba(acc, 70)}; selection-color: {fg}; }}
        QPushButton {{ background: {inp}; border: 1px solid {line}; border-radius: 10px; padding: 8px 16px; font-weight: 600; }}
        QPushButton:hover {{ background: {hov}; }}
        QPushButton#primary {{ background: {acc.name()}; border: 0; color: {on_acc(acc).name()}; }}
        QPushButton#primary:hover {{ background: {acc.lighter(112).name()}; }}
        QScrollArea {{ background: transparent; border: 0; }}
        QScrollBar:vertical {{ width: 8px; background: transparent; margin: 2px; }}
        QScrollBar::handle:vertical {{ background: {sub}; border-radius: 3px; min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QToolTip {{ background: {bg}; color: {fg}; border: 1px solid {line}; padding: 4px 8px; }}
        """

    def restyle(s):
        s.setStyleSheet(s.sheet())
        fg = '#141416' if STYLE['light'] else '#f2f2f5'
        for i, (ic, _, _) in enumerate(s.pages):
            s.nav.item(i).setIcon(vicon(ic, fg, 20))
        s._sync_cards()
        s._titlebar()

    def _titlebar(s):
        try:   # тёмный/светлый заголовок окна в тон теме (Windows 10 2004+ / 11)
            v = ctypes.c_int(0 if STYLE['light'] else 1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(s.winId()), 20, ctypes.byref(v), 4)
        except Exception:
            pass

    def showEvent(s, e):
        super().showEvent(e)
        s._titlebar()
        s._tm.start(1000)

    def hideEvent(s, e):
        s._tm.stop()
        super().hideEvent(e)

    # ---------- конструкторы строк ----------
    def _page(s):
        host = QWidget()
        v = QVBoxLayout(host)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(8)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.viewport().setAutoFillBackground(False)
        sc.setWidget(host)
        s.stack.addWidget(sc)
        return v

    def _section(s, v, title):
        lab = QLabel(title.upper())
        lab.setObjectName('sec_t')
        v.addSpacing(6)
        v.addWidget(lab)
        f = QFrame()
        f.setObjectName('sec')
        fv = QVBoxLayout(f)
        fv.setContentsMargins(16, 6, 16, 6)
        fv.setSpacing(0)
        v.addWidget(f)
        return fv

    def _row(s, fv, label, widget, hint=''):
        r = QWidget()
        h = QHBoxLayout(r)
        h.setContentsMargins(0, 10, 0, 10)
        h.setSpacing(14)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(QLabel(label))
        if hint:
            hl = QLabel(hint)
            hl.setObjectName('hint')
            hl.setWordWrap(True)
            col.addWidget(hl)
        h.addLayout(col, 1)
        h.addWidget(widget, 0, Qt.AlignRight | Qt.AlignVCenter)
        fv.addWidget(r)

    def _set(s, key, val):
        s.cfg[key] = val
        s.isl.apply_settings(style=key in STYLE_KEYS, window=key in WINDOW_KEYS, place=key in PLACE_KEYS)
        if key in STYLE_KEYS:
            QTimer.singleShot(40, s.restyle)
            QTimer.singleShot(480, s.restyle)       # после завершения анимации акцента

    def _toggle(s, key, default):
        t = Toggle(bool(s.cfg.get(key, default)))
        t.toggled.connect(lambda v: s._set(key, bool(v)))
        return t

    def _combo(s, key, items, default):
        c = QComboBox()
        for k, n in items:
            c.addItem(n, k)
        c.setCurrentIndex(max(c.findData(s.cfg.get(key, default)), 0))
        c.setMinimumWidth(230)
        c.currentIndexChanged.connect(lambda _=0: s._set(key, c.currentData()))
        return c

    def _slider(s, key, lo, hi, default, fmt, cast=float):
        host = QWidget()
        h = QHBoxLayout(host)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        sl = Slider()
        sl.setFixedWidth(180)
        lab = QLabel()
        lab.setFixedWidth(58)
        lab.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cur = float(s.cfg.get(key, default))
        sl.setValue(int(round((cur - lo) / (hi - lo) * 100)))
        lab.setText(fmt(cur))

        def changed(v):
            val = cast(round(lo + (hi - lo) * v / 100.0, 3))
            lab.setText(fmt(val))
            s._set(key, val)
        sl.valueChanged.connect(changed)
        h.addWidget(sl)
        h.addWidget(lab)
        return host

    # ---------- страницы ----------
    def _pg_general(s):
        v = s._page()
        f = s._section(v, 'Расположение')
        mons = [(i, f"Монитор {i + 1}" + (' (основной)' if i == 0 else '')) for i in range(len(QGuiApplication.screens()))]
        s._row(f, 'Монитор', s._combo('monitor', mons, 0))
        scales = [('auto', 'Авто (по разрешению экрана)'), ('0.9', '90%'), ('1.0', '100%'), ('1.15', '115%'), ('1.3', '130%'), ('1.5', '150%')]
        s._row(f, 'Масштаб интерфейса', s._combo('ui_scale', scales, 'auto'), 'Применяется после перезапуска')
        s._row(f, 'Смещение по горизонтали', s._slider('offset_x', -400, 400, 0, lambda x: f"{x:+.0f} px", int))
        fits = [('smart_dodge', 'Умный обход вкладок'), ('titlebar_snap', 'Сдвиг правее вкладок'),
                ('workarea', 'Резерв рабочей области'), ('normal', 'Обычный поверх окон')]
        s._row(f, 'Интеграция с окнами', s._combo('window_fit', fits, 'smart_dodge'),
               'Как остров ведёт себя над вкладками браузера')
        b = QPushButton('Скопировать CSS')
        b.clicked.connect(s.isl.copy_browser_notch_css)
        s._row(f, 'Вырез под остров в браузере', b, 'Для Firefox / Zen — вставьте в userChrome.css')

        f = s._section(v, 'Умное скрытие')
        s._row(f, 'Сворачиваться в линию', s._toggle('auto_peek', True), 'В развёрнутых окнах остров через паузу превращается в тонкую линию у края')
        s._row(f, 'Пауза до сворачивания', s._slider('peek_after', 1.0, 15.0, 4.0, lambda x: f"{x:.0f} с"))
        s._row(f, 'Задержка раскрытия', s._slider('open_delay', 0.0, 0.6, 0.12, lambda x: f"{x * 1000:.0f} мс"), 'Курсор должен задержаться у грани — случайные касания игнорируются. Alt — мгновенно')
        ed_h = QLineEdit(s.cfg.get('hide_apps', ''))
        ed_h.setPlaceholderText('vlc.exe, mpv.exe, powerpnt.exe')
        ed_h.setMinimumWidth(230)
        ed_h.editingFinished.connect(lambda: s._set('hide_apps', ed_h.text().strip()))
        s._row(f, 'Прятать для программ', ed_h, 'Имена процессов через запятую: пока они в фокусе, остров скрыт')

        f = s._section(v, 'Поведение')
        s._row(f, 'Запускать вместе с Windows', s._toggle('autostart', False))
        s._row(f, 'Сквозной режим', s._toggle('click_through', False), 'Остров пропускает все клики мыши')
        s._row(f, 'Показывать на скриншотах и записи', s._toggle('show_in_capture', False))
        ed = QLineEdit(s.cfg.get('city', 'Москва'))
        ed.setMinimumWidth(230)
        ed.editingFinished.connect(lambda: (s._set('city', ed.text().strip() or 'Москва'), s.isl.fetch_weather()))
        s._row(f, 'Город для погоды', ed)
        v.addStretch()

    def _pg_look(s):
        v = s._page()
        f = s._section(v, 'Тема')
        host = QWidget()
        g = QGridLayout(host)
        g.setContentsMargins(0, 12, 0, 12)
        g.setSpacing(10)
        s.cards = {}
        for i, k in enumerate(list(THEMES) + ['system']):
            c = ThemeCard(k)
            c.picked.connect(s._pick_theme)
            s.cards[k] = c
            g.addWidget(c, i // 4, i % 4)
        f.addWidget(host)

        f = s._section(v, 'Акцентный цвет')
        mode = s.cfg.get('accent_mode', 'theme')
        s.seg_acc = Segmented([('theme', 'Из темы'), ('cover', 'Из обложки'), ('custom', 'Свой')], mode)
        s.seg_acc.setMinimumWidth(270)
        s.seg_acc.changed.connect(s._pick_accent_mode)
        s._row(f, 'Источник акцента', s.seg_acc, 'Из обложки — остров подстраивается под играющий трек')
        s.sw_host = QWidget()
        sh = QHBoxLayout(s.sw_host)
        sh.setContentsMargins(0, 4, 0, 12)
        sh.setSpacing(8)
        for col in ACCENT_PRESETS:
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"QPushButton{{background:{col};border:2px solid rgba(255,255,255,70);border-radius:13px;padding:0}}"
                            f"QPushButton:hover{{border:2px solid #fff}}")
            b.clicked.connect(lambda _=0, c=col: s._pick_custom(c))
            sh.addWidget(b)
        more = QPushButton('Другой…')
        more.clicked.connect(s._pick_color_dialog)
        sh.addWidget(more)
        sh.addStretch()
        f.addWidget(s.sw_host)
        s.sw_host.setVisible(mode == 'custom')

        f = s._section(v, 'Анимации и вид')
        seg = Segmented([(k, n) for k, (_, _, n) in ANIM_STYLES.items()], s.cfg.get('anim_style', 'liquid'))
        seg.setMinimumWidth(270)
        seg.changed.connect(lambda k: s._set('anim_style', k))
        s._row(f, 'Стиль анимации', seg, 'Жёсткость и «пружинистость» раскрытия острова')
        s._row(f, 'Свой характер движения', s._toggle('motion_scenarios', True),
               'Меню, уведомления, музыка и системные события раскрываются по-разному: растягивание капсулы, «шлёпок», мягкая посадка')
        s._row(f, 'Цвета по ситуации', s._toggle('adaptive_color', True),
               'Музыка — цвета обложки, запись — красный, таймер — оранжевый, Bluetooth — голубой, важное уведомление — сигнал')
        s._row(f, 'Свечение', s._toggle('glow', True), 'Мягкий ореол у неоновых тем при музыке и уведомлениях')
        s._row(f, 'Эквалайзер по краю острова', s._toggle('edge_eq', True))
        s._row(f, 'Прозрачность в покое', s._slider('opacity_idle', 0.5, 1.0, 0.96, lambda x: f"{x * 100:.0f}%"))
        s._row(f, 'Прозрачность раскрытого', s._slider('opacity_open', 0.5, 1.0, 0.98, lambda x: f"{x * 100:.0f}%"))
        chars = [('none', 'Без персонажа'), ('astro', 'Астро (робот)'), ('cat', 'Кот'),
                 ('pixel', 'Пиксель'), ('eyes', 'Глазки'), ('fire', 'Костёр')]
        s._row(f, 'Персонаж в пилюле', s._combo('character', chars, 'none'))
        pills = [('normal', 'Обычная'), ('wide', 'Широкая с текстом песни'), ('mini', 'Мини-плеер')]
        s._row(f, 'Пилюля во время музыки', s._combo('pill_music', pills, 'normal'))
        v.addStretch()

    def _pg_music(s):
        v = s._page()
        f = s._section(v, 'Выбор плеера')
        s._row(f, 'Автовыбор играющего плеера', s._toggle('player_auto', True),
               'Показывать тот плеер, который включили последним')
        ed = QLineEdit(s.cfg.get('player_ignore', ''))
        ed.setPlaceholderText('chrome, discord')
        ed.setMinimumWidth(230)
        ed.editingFinished.connect(lambda: s._set('player_ignore', ed.text().strip()))
        s._row(f, 'Не показывать плееры', ed, 'Фрагменты имён через запятую')
        f = s._section(v, 'Тексты песен')
        s._row(f, 'Синхронные тексты (LRCLIB)', s._toggle('lyrics_enabled', True))
        f = s._section(v, 'Сейчас обнаружено')
        s.lb_players = QLabel('…')
        s.lb_players.setWordWrap(True)
        s.lb_players.setTextFormat(Qt.RichText)
        s.lb_players.setContentsMargins(0, 10, 0, 10)
        f.addWidget(s.lb_players)
        s._refresh_players()
        v.addStretch()

    def _pg_devices(s):
        v = s._page()
        f = s._section(v, 'Игровой режим')
        s._row(f, 'Полноэкранные приложения',
               s._combo('game_mode', [('hide', 'Прятать остров'), ('off', 'Не прятать')], 'hide'),
               'Игры, видео и презентации на весь экран')
        f = s._section(v, 'Устройства и приватность')
        s._row(f, 'Анимации подключения', s._toggle('device_events', True), 'USB-накопители, зарядка, наушники и колонки')
        s._row(f, 'Индикаторы микрофона и камеры', s._toggle('privacy_dots', True),
               'Оранжевая точка в острове — микрофон, зелёная — камера')
        f = s._section(v, 'История буфера обмена')
        s._row(f, 'Секретные данные', s._combo('clip_secret_policy', [('mask', 'Хранить зашифрованно и скрывать'), ('skip', 'Не сохранять')], 'mask'),
               'Ключи, токены, пароли, номера карт. Записи из менеджеров паролей не сохраняются никогда')
        s._row(f, 'Строки, похожие на пароль', s._toggle('clip_secret_heuristic', True), 'Считать секретом случайные наборы символов')
        s._row(f, 'Хранить записей', s._slider('clip_max_items', 50, 1000, 300, lambda v: f'{int(v)}', int))
        s._row(f, 'Хранить дней', s._slider('clip_keep_days', 1, 90, 30, lambda v: f'{int(v)}', int), 'Избранное не удаляется')
        f = s._section(v, 'Запись экрана')
        s._row(f, 'Системный звук', s._toggle('rec_audio_system', True), 'Нужны pyaudiowpatch и imageio-ffmpeg')
        s._row(f, 'Микрофон', s._toggle('rec_audio_mic', False))
        s._row(f, 'Максимум минут', s._slider('rec_max_min', 1, 120, 30, lambda v: f'{int(v)} мин', int), 'Запись остановится сама')
        v.addStretch()

    def _pg_ai(s):
        v = s._page()
        f = s._section(v, 'ИИ-ассистент')
        s.ed_ai_url = QLineEdit(s.cfg.get('ai_url', ''))
        s.ed_ai_key = QLineEdit(dpapi_decrypt(s.cfg.get('ai_key_enc', '')))
        s.ed_ai_key.setEchoMode(QLineEdit.Password)
        s.ed_ai_mod = QLineEdit(s.cfg.get('ai_model', 'gpt-4o-mini'))
        for w in (s.ed_ai_url, s.ed_ai_key, s.ed_ai_mod):
            w.setMinimumWidth(300)
        s._row(f, 'API URL (HTTPS)', s.ed_ai_url)
        s._row(f, 'API-ключ', s.ed_ai_key, 'Хранится зашифрованным (Windows DPAPI)')
        s._row(f, 'Модель', s.ed_ai_mod)
        s.ed_ai_sys = QLineEdit(s.cfg.get('ai_system', ''))
        s.ed_ai_sys.setMinimumWidth(300)
        s._row(f, 'Системная подсказка', s.ed_ai_sys, 'Задаёт стиль ответов; отправляется с каждым запросом')
        s._row(f, 'Память диалога', s._slider('ai_ctx_chars', 4000, 100000, 24000, lambda v: f'{int(v) // 1000}k', int),
               'Сколько символов истории уходит модели; старое отбрасывается')
        f = s._section(v, 'Чат и голос')
        s._row(f, 'Не закрывать остров в чате', s._toggle('chat_keep_open', True),
               'Пока открыта вкладка «Чат», клик вне острова его не сворачивает. Закрыть: кнопка ▾, Esc или «закрой остров»')
        s._row(f, 'Язык голоса', s._combo('voice_lang', [('ru-RU', 'Русский'), ('en-US', 'English'), ('uk-UA', 'Українська')], 'ru-RU'),
                'Распознавание речи через онлайн-сервис Google; микрофон слушает только после нажатия на кнопку')
        f = s._section(v, 'Ссылки на скриншоты')
        s._row(f, 'Сервис', s._combo('upload_service', [('none', 'Не загружать'), ('imgbb', 'ImgBB'), ('imgur', 'Imgur')], 'none'))
        s.ed_up_key = QLineEdit(dpapi_decrypt(s.cfg.get('upload_key_enc', '')))
        s.ed_up_key.setEchoMode(QLineEdit.Password)
        s.ed_up_key.setMinimumWidth(300)
        s._row(f, 'API-ключ сервиса', s.ed_up_key, 'Хранится зашифрованным (Windows DPAPI)')
        v.addStretch()

    def _text_field(s, f, label, key, placeholder='', hint='', width=230):
        ed = QLineEdit(s.cfg.get(key, ''))
        ed.setPlaceholderText(placeholder)
        ed.setMinimumWidth(width)
        ed.editingFinished.connect(lambda: s._set(key, ed.text().strip()))
        s._row(f, label, ed, hint)

    def _time_field(s, f, label, key, hint=''):
        import re
        ed = QLineEdit(s.cfg.get(key, ''))
        ed.setPlaceholderText('23:00')
        ed.setFixedWidth(90)

        def done():
            t = ed.text().strip()
            if t and not re.fullmatch(r'([01]?\d|2[0-3]):[0-5]\d', t):
                ed.setText(s.cfg.get(key, ''))                # некорректное время — возвращаем прежнее
                return
            s._set(key, t)
        ed.editingFinished.connect(done)
        s._row(f, label, ed, hint)

    def _pg_notif(s):
        v = s._page()
        f = s._section(v, 'Центр уведомлений')
        s._row(f, 'Читать уведомления Windows', s._toggle('notif_enabled', True),
               'Параметры Windows → Конфиденциальность → Уведомления должны разрешать доступ')
        s._row(f, 'Счётчик на острове', s._toggle('notif_badge', True), 'Точка или число непрочитанных на пилюле и вкладке')
        b = QPushButton('Параметры уведомлений Windows')
        b.clicked.connect(lambda: open_settings('ms-settings:notifications'))
        s._row(f, 'Баннеры Windows', b, 'Чтобы Windows не дублировала остров своими баннерами, отключите их там')
        f = s._section(v, 'Приоритеты')
        modes = [('card', 'Расширенная карточка'), ('toast', 'Короткий тост'), ('silent', 'Только в истории')]
        s._row(f, 'Важные', QLabel('всегда карточка'), 'Мессенджеры, звонки, коды подтверждения и ваши слова')
        s._row(f, 'Время показа важных', s._slider('notif_important_secs', 5, 60, 15, lambda x: f"{x:.0f} с", int), 'Наведение курсора продлевает показ')
        s._row(f, 'Системные', s._combo('notif_system', modes, 'toast'), 'Windows Security, обновления, батарея, события острова')
        s._row(f, 'Обычные', s._combo('notif_normal', modes, 'toast'))
        s._text_field(f, 'Свои важные приложения', 'notif_important_apps', 'steam, gmail', 'Фрагменты имён через запятую')
        s._text_field(f, 'Слова, делающие важным', 'notif_keywords', 'дедлайн, пожар', 'Ищутся в заголовке и тексте')
        s._text_field(f, 'Не показывать от', 'notif_muted_apps', 'spotify, reddit', 'Такие уведомления не попадают даже в историю')
        f = s._section(v, 'Не беспокоить')
        s._row(f, 'Включить сейчас', s._toggle('notif_dnd', False))
        s._row(f, 'Пропускать важные', s._toggle('notif_dnd_important', True), 'В режиме «Не беспокоить» и в тихие часы')
        s._time_field(f, 'Тихие часы: с', 'notif_quiet_from', 'Например 23:00')
        s._time_field(f, 'Тихие часы: до', 'notif_quiet_to', 'Например 08:00')
        f = s._section(v, 'Ответ и история')
        s._row(f, 'Вставлять ответ автоматически', s._toggle('notif_autopaste', False),
               'Windows не позволяет отвечать за другие приложения: остров открывает приложение и копирует ответ; с этой опцией ещё и нажимает Ctrl+V. Enter — вы')
        s._row(f, 'Убирать из центра Windows', s._toggle('notif_clear_windows', False), 'Когда вы отметили уведомление прочитанным')
        s._row(f, 'Сразу показывать картинки по ссылкам', s._toggle('notif_auto_links', False),
               'Выключено: картинка по ссылке из сообщения грузится по кнопке — иначе отправитель узнаёт, что вы прочитали. Локальные файлы показываются всегда')
        s._row(f, 'Хранить историю, дней', s._slider('notif_keep_days', 1, 90, 30, lambda x: f"{x:.0f}", int))
        v.addStretch()

    def _pg_about(s):
        v = s._page()
        f = s._section(v, APP_NAME)
        info = QLabel(f'Версия {APP_VER}\nНастройки: {CFG_PATH}\nЖурнал: {LOG_PATH}')
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        info.setWordWrap(True)
        info.setContentsMargins(0, 12, 0, 12)
        f.addWidget(info)
        f = s._section(v, 'Обслуживание')

        def open_path(pth):
            try:
                pth = Path(pth)
                if not pth.suffix:
                    pth.mkdir(parents=True, exist_ok=True)
                os.startfile(str(pth))
            except Exception:
                s.isl.pop('Не удалось открыть', str(pth)[-40:], (QColor('#ff453a'), 'folder'))
        for text, pth in (('Папка настроек', CFG_PATH.parent), ('Папка скриншотов', SHOTS_DIR)):
            b = QPushButton('Открыть')
            b.clicked.connect(lambda _=0, p_=pth: open_path(p_))
            s._row(f, text, b)
        b_log = QPushButton('Открыть')
        b_log.clicked.connect(lambda: open_path(LOG_PATH) if LOG_PATH.exists() else s.isl.pop('Журнал пуст', 'Ошибок нет', (QColor('#34c759'), 'check')))
        s._row(f, 'Журнал ошибок', b_log)

        b_reset = QPushButton('Сбросить')
        def reset():
            if getattr(b_reset, 'armed', 0) > time.time():
                for k in ('theme', 'accent_mode', 'accent_custom', 'anim_style', 'motion_scenarios', 'adaptive_color', 'glow', 'opacity_idle', 'opacity_open',
                          'scale', 'offset_x', 'character', 'pill_music', 'edge_eq'):
                    s.cfg[k] = DEFAULT_CFG[k]
                s.saved = True
                save_cfg(s.cfg)
                s.isl.apply_settings()
                s.close()
                QTimer.singleShot(80, s.isl.open_settings)
            else:
                b_reset.armed = time.time() + 3
                b_reset.setText('Точно сбросить?')
                QTimer.singleShot(3000, lambda: b_reset.setText('Сбросить'))
        b_reset.clicked.connect(reset)
        s._row(f, 'Оформление по умолчанию', b_reset, 'Тема, акцент, анимации, прозрачность, размер')
        v.addStretch()

    # ---------- обработчики ----------
    def _sync_cards(s):
        cur = s.cfg.get('theme', 'obsidian')
        cur = 'obsidian' if cur == 'dark' else cur
        for k, c in getattr(s, 'cards', {}).items():
            c.sel = (k == cur)
            c.update()

    def _pick_theme(s, key):
        s._set('theme', key)
        s._sync_cards()

    def _pick_accent_mode(s, mode):
        s.sw_host.setVisible(mode == 'custom')
        s._set('accent_mode', mode)

    def _pick_custom(s, col):
        s.cfg['accent_custom'] = col
        s.seg_acc.setCurrent('custom')
        s._set('accent_mode', 'custom')

    def _pick_color_dialog(s):
        c = QColorDialog.getColor(QColor(s.cfg.get('accent_custom', '#ff4d6d')), s, 'Акцентный цвет')
        if c.isValid():
            s._pick_custom(c.name())

    def _refresh_players(s):
        rows = getattr(s.isl, 'players', [])
        if not rows:
            s.lb_players.setText('Плееры не найдены. Запустите музыку или видео — они появятся здесь.')
            return
        lines = []
        for r in rows:
            mark = ' · <i>играет</i>' if r['playing'] else ''
            ttl = html.escape((r['title'] or '—')[:60])
            lines.append(f"<span style='color:{r['color']}'>●</span> <b>{html.escape(r['name'])}</b> — {ttl}{mark}")
        s.lb_players.setText('<br>'.join(lines))

    def _rollback(s):
        s.cfg.clear()
        s.cfg.update(s.orig)
        s.isl.apply_settings()

    def save(s):
        c = s.cfg
        c['ai_url'] = s.ed_ai_url.text().strip()
        c['ai_key_enc'] = dpapi_encrypt(s.ed_ai_key.text().strip())
        c['ai_model'] = s.ed_ai_mod.text().strip() or 'gpt-4o-mini'
        c['ai_system'] = s.ed_ai_sys.text().strip() or DEFAULT_CFG['ai_system']
        c['upload_key_enc'] = dpapi_encrypt(s.ed_up_key.text().strip())
        if not set_autostart(bool(c.get('autostart'))):
            c['autostart'] = autostart_enabled()
        save_cfg(c)
        s.saved = True
        s.isl.apply_settings()
        s.isl.fetch_weather()
        s.isl.pop('Настройки сохранены', 'Изменения применены', (STYLE['acc'], 'check'), 2.4)
        s.accept()

    def reject(s):
        if not s.saved:
            s._rollback()
        super().reject()
