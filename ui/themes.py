"""Темы, акцентные цвета, смешивание цветов, QSS и миксин смены темы острова."""
import importlib
import re
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget
from core.win32 import is_win_light


# ---- Темы: base/base2 — градиент тела острова, card_end — конец градиента карточек, border — альфа рамки ----
THEMES = {
    'obsidian': dict(name='Обсидиан', light=False, base='#070709', base2='#120f17', acc='#ff4d6d', card_end='#121215', border=36),
    'oled':     dict(name='OLED',     light=False, base='#000000', base2='#000000', acc='#e8e8ee', card_end='#050505', border=24),
    'graphite': dict(name='Графит',   light=False, base='#1b1b1e', base2='#27272c', acc='#0a84ff', card_end='#202024', border=30),
    'aurora':   dict(name='Аврора',   light=False, base='#0a0f24', base2='#1d1448', acc='#7c5cff', card_end='#0e1430', border=46, glow=True),
    'neon':     dict(name='Неон',     light=False, base='#06050e', base2='#130a26', acc='#00f0ff', card_end='#0a0818', border=80, glow=True),
    'sunset':   dict(name='Закат',    light=False, base='#150a0b', base2='#2d1117', acc='#ff7a45', card_end='#1a0d10', border=42, glow=True),
    'emerald':  dict(name='Изумруд',  light=False, base='#050f0b', base2='#0b2219', acc='#2ee59d', card_end='#08140f', border=42, glow=True),
    'light':    dict(name='Светлая',  light=True,  base='#f4f4f9', base2='#e6e6ee', acc='#ff4d6d', card_end='#e8e8ed', border=40),
    'sakura':   dict(name='Сакура',   light=True,  base='#fff3f7', base2='#ffe2ec', acc='#ff5c8a', card_end='#ffe7ef', border=46),
}

ACCENT_PRESETS = ['#ff4d6d', '#ff7a45', '#ffd60a', '#34c759', '#2ee59d', '#00f0ff', '#0a84ff', '#7c5cff', '#bf5af2', '#ff5c8a']

STYLE = {'acc': QColor('#ff4d6d'), 'light': False, 'key': 'obsidian', 'th': THEMES['obsidian']}

FF = "'Segoe UI Variable Text','Segoe UI'"

FD = "'Segoe UI Variable Display','Segoe UI Semibold','Segoe UI'"


def mix(c1, c2, k):
    return QColor(
        int(c1.red() * (1 - k) + c2.red() * k),
        int(c1.green() * (1 - k) + c2.green() * k),
        int(c1.blue() * (1 - k) + c2.blue() * k)
    )


def resolve_theme(cfg) -> str:
    """Возвращает ключ темы с учётом старых значений конфига (dark/light/system)."""
    key = cfg.get('theme', 'obsidian')
    if key == 'dark':
        key = 'obsidian'
    if key == 'system':
        key = 'light' if is_win_light() else 'obsidian'
    return key if key in THEMES else 'obsidian'


def apply_style(cfg):
    key = resolve_theme(cfg)
    STYLE.update(key=key, th=THEMES[key], light=THEMES[key]['light'])


def rgba(c: QColor, a=None) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha() if a is None else a})"


def on_acc(c: QColor) -> QColor:
    """Цвет текста поверх акцента: тёмный на светлых акцентах (циан, жёлтый), белый на тёмных."""
    luma = (0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()) / 255.0
    return QColor('#141416') if luma > 0.6 else QColor('white')


def qss(acc, light=False):
    th = STYLE['th']
    fg = '#141416' if light else '#ffffff'
    sub = 'rgba(20,20,22,150)' if light else 'rgba(255,255,255,155)'
    e = '0,0,0' if light else '255,255,255'
    btn_bg = f'rgba({e},{14 if light else 15})'
    btn_hv = f'rgba({e},{26 if light else 28})'
    dock_bg = f'rgba({e},{10 if light else 9})'
    line = f'rgba({e},{18 if light else 14})'
    card_end = th['card_end']
    c_start = mix(acc, QColor('#ffffff' if light else '#000000'), 0.45).name()
    return f"""
    * {{ color: {fg}; font-family: {FF}; font-size: 12.5px; }}
    QPushButton, QToolButton {{
        background: {btn_bg}; border: 1px solid {line};
        border-radius: 13px; padding: 7px 10px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {btn_hv}; }}
    QPushButton:pressed {{ background: rgba({e},40); }}
    #card {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {c_start}, stop:1 {card_end});
        border-radius: 20px; border: 1px solid rgba({e},20);
    }}
    #bento {{
        background: {btn_bg}; border-radius: 16px; border: 1px solid {line};
    }}
    #dock {{
        background: {dock_bg}; border-radius: 18px; border: 1px solid {line};
    }}
    #skycard {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #2b5876, stop:1 #4e4376);
        border-radius: 20px; color: #fff;
    }}
    #skycard QLabel {{ color: #fff; background: transparent; }}
    QLineEdit, QTextEdit, QListWidget, QComboBox {{
        background: {btn_bg}; border: 1px solid {line};
        border-radius: 12px; padding: 6px 10px; outline: 0;
    }}
    QListWidget::item {{ padding: 6px 8px; border-radius: 9px; }}
    QListWidget::item:hover, QListWidget::item:selected {{ background: {btn_hv}; }}
    QScrollBar:vertical {{ width: 4px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {sub}; border-radius: 2px; }}
    """


def menu_qss():
    """Стиль контекстных меню (трей, выбор плеера) под текущую тему."""
    th, lt = STYLE['th'], STYLE['light']
    bg = '#f8f8fb' if lt else mix(QColor(th['base']), QColor('#2a2a31'), .6).name()
    fg = '#141416' if lt else '#f2f2f5'
    sub = 'rgba(20,20,22,130)' if lt else 'rgba(255,255,255,120)'
    e = '0,0,0' if lt else '255,255,255'
    hov = rgba(STYLE['acc'], 55)
    return f"""
    QMenu {{ background: {bg}; border: 1px solid rgba({e},30); border-radius: 14px; padding: 6px; }}
    QMenu::item {{ color: {fg}; padding: 7px 18px 7px 8px; border-radius: 8px; margin: 1px 0; font-family: {FF}; font-size: 12.5px; }}
    QMenu::item:selected {{ background: {hov}; }}
    QMenu::item:disabled {{ color: {sub}; }}
    QMenu::separator {{ height: 1px; background: rgba({e},22); margin: 5px 8px; }}
    QMenu::icon {{ padding-left: 8px; }}
    QMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
    QMenu::right-arrow {{ margin-right: 8px; }}
    """

_INLINE_WHITE = re.compile(r'(?<![-\w])color\s*:\s*rgba\(\s*255\s*,\s*255\s*,\s*255\s*,')

_INLINE_HEX = re.compile(r'(?<![-\w])color\s*:\s*(?:#fff(?:fff)?|white)\b', re.I)


def _in_skycard(w) -> bool:
    p = w.parent()
    while p is not None:
        if p.objectName() == 'skycard':
            return True
        p = p.parent()
    return False


def retint_inline(root, light):
    """Светлые темы: перекрашивает «зашитые» белые цвета текста из inline-стилей виджетов.
    Оригинал стиля запоминается, поэтому переключение тема↔тема обратимо."""
    for w in root.findChildren(QWidget):
        cur = w.styleSheet()
        if not cur or w.property('keep_colors') or _in_skycard(w):       # keep_colors: виджет сам красит текст под фон (пузырь чата)
            continue
        if cur != w.property('_ss_set'):          # стиль выставлен снаружи → это новый «оригинал»
            w.setProperty('_ss_orig', cur)
        base = w.property('_ss_orig') or cur
        new = base
        if light:
            new = _INLINE_HEX.sub('color:#141416', _INLINE_WHITE.sub('color:rgba(20,20,22,', base))
        if new != cur:
            w.setStyleSheet(new)
        w.setProperty('_ss_set', new)


def wr(m):
    try:
        return importlib.import_module('winrt.' + m)
    except ImportError:
        return importlib.import_module('winsdk.' + m)


class ThemeMixin:
    """Часть класса Island: ThemeMixin."""

    # ==================== ТЕМЫ, АКЦЕНТ, НАСТРОЙКИ «НА ЛЕТУ» ====================
    def update_theme_flag(s):
        apply_style(s.cfg)

    def target_acc(s) -> QColor:
        mode = s.cfg.get('accent_mode', 'theme')
        if mode == 'custom':
            return QColor(s.cfg.get('accent_custom', '#ff4d6d'))
        if mode == 'cover' and s.cover_acc is not None:
            return QColor(s.cover_acc)
        return QColor(STYLE['th']['acc'])

    def refresh_accent(s, animate=True):
        """Плавно перетекает к целевому акценту (тема / обложка / свой цвет)."""
        tgt = s.target_acc()
        if s._acc_running:
            if s.acc_anim.endValue() == tgt:
                return
            s.acc_anim.stop()
        elif tgt == s.acc:
            return
        if not animate or not s.isVisible():
            s._acc_live(tgt)
            s._acc_done()
            return
        s._acc_running = True
        s.acc_anim.setStartValue(QColor(s.acc))
        s.acc_anim.setEndValue(tgt)
        s.acc_anim.start()

    def _acc_live(s, c):
        s.acc = QColor(c)
        STYLE['acc'] = s.acc
        if getattr(s, 'pp', None) is not None:
            s.pp.badge_col = s.acc

    def _acc_done(s):
        s._acc_running = False
        s._acc_live(s.target_acc())
        s.restyle()
        if getattr(s, 'tray', None) is not None:
            s.tray.setIcon(s.make_tray_icon())

    def restyle(s):
        """Полная перекраска панели: QSS темы + inline-стили светлых тем. Дорого — вызываем только при смене темы/акцента."""
        s.inner.setStyleSheet(qss(s.acc, STYLE['light']))
        retint_inline(s.inner, STYLE['light'])
        s.chat_restyle()
        s.update()
