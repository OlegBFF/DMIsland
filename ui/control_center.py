"""Панель управления: Wi-Fi, Bluetooth, громкость и микшер приложений, устройства звука, яркость, микрофон, камера,
энергосбережение и режим Windows. Все состояния приходят из SystemHub (реальные данные Windows), сюда они только рисуются."""
import ctypes
from PySide6.QtCore import QRect, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QScrollArea, QStackedWidget,
    QToolTip, QVBoxLayout, QWidget,
)
from system.util import open_settings
from ui.icons import VectorIcon
from ui.themes import STYLE
from ui.widgets import Slider, Toggle, VectorBtn, fnt

PG_HOME, PG_WIFI, PG_BT, PG_AUDIO, PG_POWER, PG_MODE = range(6)

BLUE, ORANGE, GREEN, PURPLE = QColor('#0a84ff'), QColor('#ff9f0a'), QColor('#30d158'), QColor('#5e5ce6')


def _fg():
    return QColor('#141416') if STYLE['light'] else QColor('white')


def _muted():
    return QColor(20, 20, 22, 140) if STYLE['light'] else QColor(255, 255, 255, 140)


def _card_bg(on=False, col=None):
    if on and col is not None:
        c = QColor(col)
        c.setAlpha(70 if not STYLE['light'] else 60)
        return c
    return QColor(0, 0, 0, 14) if STYLE['light'] else QColor(255, 255, 255, 15)


class Tile(QWidget):
    """Плитка быстрого действия. Клик — действие, «›» справа сверху — подробности."""
    clicked = Signal()
    detail = Signal()

    def __init__(s, icon, title, col, has_detail=True):
        super().__init__()
        s.icon, s.title, s.col, s.has_detail = icon, title, col, has_detail
        s.on, s.sub, s.avail, s.busy = False, '', True, False
        s.setMinimumHeight(92)
        s.setCursor(Qt.PointingHandCursor)

    def set_state(s, on, sub, avail=True):
        if (on, sub, avail, s.busy) != (s.on, s.sub, s.avail, False):
            s.on, s.sub, s.avail, s.busy = bool(on), sub, avail, False
            s.update()

    def set_busy(s):
        s.busy, s.sub = True, 'Переключаю…'
        s.update()

    def _chev(s):
        return QRectF(s.width() - 38, 6, 32, 32)

    def mousePressEvent(s, e):
        if e.button() != Qt.LeftButton:
            return
        if s.has_detail and s._chev().contains(e.position()):
            s.detail.emit()
        else:
            s.clicked.emit()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(1.0 if s.avail else 0.45)
        r = QRectF(0.5, 0.5, s.width() - 1, s.height() - 1)
        hv = s.underMouse() and s.avail
        bg = _card_bg(s.on, s.col)
        if hv:
            bg.setAlpha(min(255, bg.alpha() + 14))
        edge = QColor(s.col) if s.on else QColor(255, 255, 255, 18)
        if s.on:
            edge.setAlpha(120)
        p.setPen(QPen(edge, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 16, 16)
        VectorIcon.draw(p, s.icon, QRectF(12, 12, 30, 30), QColor('white') if s.on else _fg(), s.col if s.on else None)
        if s.has_detail:
            p.setPen(_muted())
            p.setFont(fnt(14, QFont.DemiBold))
            p.drawText(s._chev(), Qt.AlignCenter, '›')
        p.setPen(_fg())
        p.setFont(fnt(10, QFont.DemiBold))
        p.drawText(QRectF(12, s.height() - 44, s.width() - 20, 20), Qt.AlignVCenter | Qt.AlignLeft, s.title)
        p.setPen(_muted())
        p.setFont(fnt(8.8))
        sub = QFontMetrics(p.font()).elidedText(s.sub, Qt.ElideRight, int(s.width() - 24))
        p.drawText(QRectF(12, s.height() - 25, s.width() - 20, 18), Qt.AlignVCenter | Qt.AlignLeft, sub)

    def enterEvent(s, e):
        s.update()

    def leaveEvent(s, e):
        s.update()


class Row(QWidget):
    """Строка списка: название, подпись, значение справа и галочка."""
    clicked = Signal()

    def __init__(s, clickable=True):
        super().__init__()
        s.data = None
        s.title, s.sub, s.right, s.checked, s.dot = '', '', '', False, None
        s.setFixedHeight(46)
        if clickable:
            s.setCursor(Qt.PointingHandCursor)
        s._clickable = clickable

    def set(s, title, sub='', right='', checked=False, dot=None):
        s.title, s.sub, s.right, s.checked, s.dot = title, sub, right, checked, dot
        s.update()

    def mousePressEvent(s, e):
        if s._clickable and e.button() == Qt.LeftButton:
            s.clicked.emit()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(_card_bg(s.checked, STYLE['acc']) if s.checked else (QColor(255, 255, 255, 22) if (s.underMouse() and s._clickable) else QColor(0, 0, 0, 0)))
        if STYLE['light'] and s.underMouse():
            p.setBrush(QColor(0, 0, 0, 16))
        p.drawRoundedRect(QRectF(0, 1, s.width(), s.height() - 2), 12, 12)
        x = 12
        if s.dot is not None:
            p.setBrush(s.dot)
            p.drawEllipse(QRectF(12, s.height() / 2 - 4, 8, 8))
            x = 30
        fm_w = s.width() - x - 90
        p.setPen(_fg())
        p.setFont(fnt(10, QFont.DemiBold))
        p.drawText(QRectF(x, 5 if s.sub else 0, fm_w, 20 if s.sub else s.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(s.title, Qt.ElideRight, int(fm_w)))
        if s.sub:
            p.setPen(_muted())
            p.setFont(fnt(8.6))
            p.drawText(QRectF(x, 24, fm_w, 16), Qt.AlignVCenter | Qt.AlignLeft, s.sub)
        p.setPen(_muted())
        p.setFont(fnt(10))
        p.drawText(QRectF(s.width() - 84, 0, 54, s.height()), Qt.AlignVCenter | Qt.AlignRight, s.right)
        if s.checked:
            p.setPen(QPen(STYLE['acc'], 2.2, Qt.SolidLine, Qt.RoundCap))
            cx, cy = s.width() - 18, s.height() / 2
            p.drawLine(int(cx - 5), int(cy), int(cx - 1.5), int(cy + 4))
            p.drawLine(int(cx - 1.5), int(cy + 4), int(cx + 5), int(cy - 4))

    def enterEvent(s, e):
        s.update()

    def leaveEvent(s, e):
        s.update()


class AppRow(QWidget):
    """Громкость одного приложения: название, ползунок, значение, mute."""

    def __init__(s, on_volume, on_mute):
        super().__init__()
        s.data = None
        h = QHBoxLayout(s)
        h.setContentsMargins(8, 2, 4, 2)
        h.setSpacing(8)
        s.name = QLabel()
        s.name.setFixedWidth(130)
        s.sl = Slider()
        s.val = QLabel('0')
        s.val.setFixedWidth(28)
        s.val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        s.val.setStyleSheet('color:rgba(255,255,255,150);font-size:11px;border:0;background:transparent')
        s.mute = QPushButton('🔊')
        s.mute.setFixedSize(30, 26)
        s.mute.setCursor(Qt.PointingHandCursor)
        s.sl.valueChanged.connect(lambda v: (s.val.setText(str(v)), on_volume(s.data['name'], v)))
        s.mute.clicked.connect(lambda: on_mute(s.data['name'], not s.data['muted']))
        for w in (s.name, s.sl, s.val, s.mute):
            h.addWidget(w, 1 if w is s.sl else 0)
        s.setFixedHeight(34)

    def apply(s, d):
        s.data = d
        s.name.setText(QFontMetrics(s.name.font()).elidedText(d['name'], Qt.ElideRight, 126))
        if not s.sl.drag:
            s.sl.setValue(d['volume'])
            s.val.setText(str(d['volume']))
        s.mute.setText('🔇' if d['muted'] else '🔊')


class KeyedRows:
    """Синхронизирует список виджетов с набором ключей без пересоздания: ползунки и наведение не «моргают»."""

    def __init__(s, layout, factory):
        s.layout, s.factory, s.w = layout, factory, {}

    def sync(s, items, update, at=0):
        keys = [k for k, _ in items]
        for k in [k for k in s.w if k not in keys]:
            w = s.w.pop(k)
            s.layout.removeWidget(w)
            w.deleteLater()
        for k, d in items:
            if k not in s.w:
                s.w[k] = s.factory()
                s.layout.insertWidget(at + len(s.w) - 1, s.w[k])
            update(s.w[k], d)


class DetailPage(QWidget):
    def __init__(s, title, back, header_widgets=()):
        super().__init__()
        v = QVBoxLayout(s)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        b = QPushButton('‹  Назад')
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(back)
        s.title = QLabel(title)
        s.title.setStyleSheet('font-weight:700;font-size:14px;border:0;background:transparent')
        top.addWidget(b)
        top.addWidget(s.title)
        top.addStretch()
        for w in header_widgets:
            top.addWidget(w)
        v.addLayout(top)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setStyleSheet('QScrollArea{background:transparent;border:0}')
        body = QWidget()
        body.setStyleSheet('background:transparent')
        s.body = QVBoxLayout(body)
        s.body.setContentsMargins(0, 0, 6, 0)
        s.body.setSpacing(2)
        s.body.addStretch()
        sc.setWidget(body)
        v.addWidget(sc, 1)

    def section(s, text):
        lb = QLabel(text.upper())
        lb.setStyleSheet('color:rgba(255,255,255,120);font-size:9.5px;font-weight:700;border:0;background:transparent;padding:6px 8px 2px 8px')
        s.body.insertWidget(s.body.count() - 1, lb)
        return lb

    def add(s, w):
        s.body.insertWidget(s.body.count() - 1, w)
        return w


def _hint(text):
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setStyleSheet('color:rgba(255,255,255,130);font-size:11px;border:0;background:transparent;padding:6px 8px')
    return lb


class ControlCenter(QStackedWidget):
    def __init__(s, isl):
        super().__init__()
        s.isl, s.hub = isl, isl.hub
        s.priv = ('', '')
        s._build_home()
        s._build_wifi()
        s._build_bt()
        s._build_audio()
        s._build_power()
        s._build_mode()
        s._scan_timer = QTimer(s)
        s._scan_timer.setInterval(15000)
        s._scan_timer.timeout.connect(s._auto_scan)
        s.currentChanged.connect(s._page_changed)
        s.apply(s.hub.state)

    # ==================== ГЛАВНАЯ ====================
    def _build_home(s):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        mid = QHBoxLayout()
        mid.setSpacing(8)

        g = QGridLayout()
        g.setSpacing(8)
        s.t_wifi = Tile('wifi', 'Wi-Fi', BLUE)
        s.t_bt = Tile('bt', 'Bluetooth', BLUE)
        s.t_mic = Tile('mic', 'Микрофон', ORANGE)
        s.t_cam = Tile('cam', 'Камера', GREEN, has_detail=False)
        s.t_pow = Tile('bat', 'Энергосбережение', GREEN)
        s.t_mode = Tile('moon', 'Режим Windows', PURPLE)
        for i, t in enumerate((s.t_wifi, s.t_bt, s.t_mic, s.t_cam, s.t_pow, s.t_mode)):
            g.addWidget(t, i // 3, i % 3)
        s.t_wifi.clicked.connect(s._toggle_wifi)
        s.t_wifi.detail.connect(lambda: s.go(PG_WIFI))
        s.t_bt.clicked.connect(s._toggle_bt)
        s.t_bt.detail.connect(lambda: s.go(PG_BT))
        s.t_mic.clicked.connect(lambda: s.hub.toggle_mute('in'))
        s.t_mic.detail.connect(lambda: s.go(PG_AUDIO))
        s.t_cam.clicked.connect(lambda: open_settings('ms-settings:privacy-webcam'))
        s.t_pow.clicked.connect(s._toggle_power)
        s.t_pow.detail.connect(lambda: s.go(PG_POWER))
        s.t_mode.clicked.connect(s.hub.toggle_winmode)
        s.t_mode.detail.connect(lambda: s.go(PG_MODE))
        mid.addLayout(g, 3)

        right = QVBoxLayout()
        right.setSpacing(8)
        vol = QFrame()
        vol.setObjectName('bento')
        vv = QVBoxLayout(vol)
        vv.setContentsMargins(12, 8, 10, 8)
        vv.setSpacing(2)
        h1 = QHBoxLayout()
        s.vol_lbl = QLabel('Громкость')
        s.vol_val = QLabel('')
        for lb in (s.vol_lbl, s.vol_val):
            lb.setStyleSheet('font-weight:600;font-size:12px;border:0;background:transparent')
        s.vol_mute = QPushButton('🔊')
        s.vol_mute.setFixedSize(34, 26)
        s.vol_mute.setCursor(Qt.PointingHandCursor)
        s.vol_mute.clicked.connect(lambda: s.hub.toggle_mute('out'))
        h1.addWidget(s.vol_lbl)
        h1.addStretch()
        h1.addWidget(s.vol_val)
        h1.addWidget(s.vol_mute)
        s.vol_sl = Slider()
        s.vol_sl.valueChanged.connect(lambda v: (s.vol_val.setText(f'{v}%'), s.hub.set_volume(v)))
        s.vol_dev = QPushButton('Устройство вывода ▾')
        s.vol_dev.setCursor(Qt.PointingHandCursor)
        s.vol_dev.setFixedHeight(26)
        s.vol_dev.setStyleSheet('font-size:11px;padding:2px 8px;border-radius:9px;text-align:left')
        s.vol_dev.clicked.connect(lambda: s.go(PG_AUDIO))
        vv.addLayout(h1)
        vv.addWidget(s.vol_sl)
        vv.addWidget(s.vol_dev)
        right.addWidget(vol, 3)

        br = QFrame()
        br.setObjectName('bento')
        bv = QVBoxLayout(br)
        bv.setContentsMargins(12, 8, 10, 8)
        bv.setSpacing(2)
        h2 = QHBoxLayout()
        s.br_lbl = QLabel('Яркость')
        s.br_lbl.setStyleSheet('font-weight:600;font-size:12px;border:0;background:transparent')
        s.br_val = QLabel('')
        s.br_val.setStyleSheet('font-weight:600;font-size:12px;border:0;background:transparent')
        h2.addWidget(s.br_lbl)
        h2.addStretch()
        h2.addWidget(s.br_val)
        s.br_sl = Slider()
        s.br_sl.valueChanged.connect(lambda v: (s.br_val.setText(f'{v}%'), s.hub.set_brightness(v)))
        bv.addLayout(h2)
        bv.addWidget(s.br_sl)
        right.addWidget(br, 2)
        mid.addLayout(right, 2)
        v.addLayout(mid, 1)

        bot = QHBoxLayout()
        bot.setSpacing(8)
        for ic, label, col, cmd, fn in (
                ('lock', 'Блокировка', BLUE, None, lambda: ctypes.windll.user32.LockWorkStation()),
                ('moon', 'Сон', PURPLE, ['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'], None),
                ('sys', 'Перезагрузка', ORANGE, ['shutdown', '/r', '/t', '0'], None),
                ('power', 'Выключение', QColor('#ff453a'), ['shutdown', '/s', '/t', '0'], None)):
            b = VectorBtn(ic, label, col, fn, h=44)
            if cmd:
                b.clicked.connect(lambda _=0, btn=b, l=label, c=cmd: s.isl.risky(btn, l, c))
            bot.addWidget(b, 1)
        v.addLayout(bot)
        s.addWidget(w)

    # ==================== WI-FI ====================
    def _build_wifi(s):
        s.wifi_tg = Toggle(False)
        s.wifi_tg.toggled.connect(lambda on: s._radio_user('wifi', on))
        rescan = QPushButton('Обновить')
        rescan.setCursor(Qt.PointingHandCursor)
        rescan.clicked.connect(s.hub.wifi_scan)
        s.pg_wifi = DetailPage('Wi-Fi', lambda: s.go(PG_HOME), (rescan, s.wifi_tg))
        s.wifi_hint = s.pg_wifi.add(_hint(''))
        s.wifi_rows = KeyedRows(s.pg_wifi.body, s._mk_wifi_row)
        s.addWidget(s.pg_wifi)

    def _mk_wifi_row(s):
        r = Row()
        r.clicked.connect(lambda r=r: s._wifi_click(r.data))
        return r

    def _wifi_click(s, d):
        if d['connected']:
            s.hub.wifi_disconnect()
        else:
            s.hub.wifi_connect(d['ssid'])

    def _toggle_wifi(s):
        w = s.hub.state.get('wifi', {})
        if w.get('present'):
            s.t_wifi.set_busy()
            s.hub.set_radio('wifi', not w.get('on'))
        else:
            open_settings('ms-settings:network-wifi')

    def _radio_user(s, name, on):
        s.hub.set_radio(name, on)

    # ==================== BLUETOOTH ====================
    def _build_bt(s):
        s.bt_tg = Toggle(False)
        s.bt_tg.toggled.connect(lambda on: s._radio_user('bt', on))
        add = QPushButton('Добавить устройство')
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(lambda: open_settings('ms-settings:bluetooth'))
        s.pg_bt = DetailPage('Bluetooth', lambda: s.go(PG_HOME), (add, s.bt_tg))
        s.bt_hint = s.pg_bt.add(_hint(''))
        s.bt_rows = KeyedRows(s.pg_bt.body, s._mk_bt_row)
        s.addWidget(s.pg_bt)

    def _mk_bt_row(s):
        r = Row()
        r.clicked.connect(lambda r=r: s.hub.bt_set_connected(r.data, not r.data['connected']))
        return r

    def _toggle_bt(s):
        b = s.hub.state.get('bt', {})
        if b.get('present'):
            s.t_bt.set_busy()
            s.hub.set_radio('bt', not b.get('on'))
        else:
            open_settings('ms-settings:bluetooth')

    # ==================== ЗВУК ====================
    def _build_audio(s):
        s.pg_audio = DetailPage('Звук', lambda: s.go(PG_HOME))
        s.pg_audio.section('Вывод')
        s.out_hint = s.pg_audio.add(_hint('Нет устройств вывода'))
        s.out_rows = KeyedRows(s.pg_audio.body, s._mk_dev_row)
        s.pg_audio.section('Ввод (микрофон)')
        s.in_hint = s.pg_audio.add(_hint('Нет микрофонов'))
        s.in_rows = KeyedRows(s.pg_audio.body, s._mk_dev_row)
        s.pg_audio.section('Громкость приложений')
        s.app_hint = s.pg_audio.add(_hint('Сейчас ни одно приложение не использует звук'))
        s.app_rows = KeyedRows(s.pg_audio.body, lambda: AppRow(s.hub.set_session_volume, s.hub.set_session_mute))
        s.addWidget(s.pg_audio)

    def _mk_dev_row(s):
        r = Row()
        r.clicked.connect(lambda r=r: s.hub.set_default_device(r.data['id'], r.data['name']))
        return r

    # ==================== ПИТАНИЕ ====================
    def _build_power(s):
        s.pg_power = DetailPage('Питание', lambda: s.go(PG_HOME))
        s.pw_info = s.pg_power.add(_hint(''))
        s.pw_rows = {}
        for key, title, sub in (('efficiency', 'Энергосбережение', 'Максимум автономности, снижена производительность'),
                                ('balanced', 'Сбалансированный', 'Режим Windows по умолчанию'),
                                ('performance', 'Производительность', 'Максимум скорости, больше расход заряда')):
            r = Row()
            r.set(title, sub)
            r.clicked.connect(lambda k=key: s.hub.set_power_mode(k))
            s.pw_rows[key] = (r, title, sub)
            s.pg_power.add(r)
        b = QPushButton('Параметры экономии заряда Windows')
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: open_settings('ms-settings:batterysaver'))
        s.pg_power.add(b)
        s.addWidget(s.pg_power)

    def _toggle_power(s):
        p = s.hub.state.get('power', {})
        if p.get('mode') is None:
            open_settings('ms-settings:batterysaver')
            return
        s.t_pow.set_busy()
        s.hub.set_power_mode('balanced' if p['mode'] == 'efficiency' else 'efficiency')

    # ==================== РЕЖИМ WINDOWS ====================
    def _build_mode(s):
        s.pg_mode = DetailPage('Режим Windows', lambda: s.go(PG_HOME))
        s.mode_tg = {}
        for key, title, sub in (('system', 'Тёмный режим Windows', 'Панель задач, меню «Пуск», центр уведомлений'),
                                ('apps', 'Тёмный режим приложений', 'Проводник, Параметры и приложения с поддержкой темы')):
            row = QFrame()
            row.setObjectName('bento')
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 12, 8)
            col = QVBoxLayout()
            t = QLabel(title)
            t.setStyleSheet('font-weight:600;font-size:12px;border:0;background:transparent')
            st = QLabel(sub)
            st.setStyleSheet('color:rgba(255,255,255,130);font-size:10.5px;border:0;background:transparent')
            col.addWidget(t)
            col.addWidget(st)
            tg = Toggle(False)
            tg.toggled.connect(lambda on, k=key: s.hub.set_winmode(**{('system_light' if k == 'system' else 'apps_light'): not on}))
            h.addLayout(col, 1)
            h.addWidget(tg)
            s.mode_tg[key] = tg
            s.pg_mode.add(row)
        b = QPushButton('Цвета и режим в Параметрах Windows')
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda: open_settings('ms-settings:colors'))
        s.pg_mode.add(b)
        s.addWidget(s.pg_mode)

    def flash(s, text):
        """Сообщение поверх открытой панели (тост закрыл бы остров, пока вы с ним работаете)."""
        QToolTip.showText(QCursor.pos(), text, s, QRect(), 3500)

    # ==================== НАВИГАЦИЯ ====================
    def go(s, page):
        s.setCurrentIndex(page)

    def _page_changed(s, i):
        if i == PG_WIFI:
            s.hub.wifi_scan()
            s._scan_timer.start()
        else:
            s._scan_timer.stop()

    def _auto_scan(s):
        if s.currentIndex() == PG_WIFI and s.hub.system_active:
            s.hub.wifi_scan()

    # ==================== ПРИЁМ СОСТОЯНИЯ ====================
    def set_privacy(s, mic, cam):
        s.priv = (mic, cam)
        s._apply_mic()
        s._apply_cam()

    @staticmethod
    def _silent(w, on):
        w.blockSignals(True)
        w.setChecked(on)
        w.blockSignals(False)

    def _apply_mic(s):
        d = s.hub.state.get('audio', {}).get('in', {})
        if d.get('volume') is None:
            s.t_mic.set_state(False, 'Нет микрофона', False)
        elif d.get('muted'):
            s.t_mic.set_state(False, 'Отключён')
        else:
            s.t_mic.set_state(True, f'Использует: {s.priv[0]}' if s.priv[0] else 'Включён')

    def _apply_cam(s):
        cam = s.priv[1]
        s.t_cam.set_state(bool(cam), f'Использует: {cam}' if cam else 'Не используется · настройки')

    def apply(s, st, changed=None):
        """st — полное слитое состояние; changed — какие ключи пришли в этом снимке (None — всё)."""
        ch = set(st) if changed is None else set(changed)
        if 'audio' in ch:
            s._apply_audio(st.get('audio', {}))
        if 'wifi' in ch or 'wifi_networks' in ch:
            s._apply_wifi(st)
        if 'bt' in ch:
            s._apply_bt(st.get('bt', {}))
        if 'brightness' in ch:
            b = st.get('brightness', {})
            ok = bool(b.get('available'))
            s.br_sl.setEnabled(ok)
            if ok and not s.br_sl.drag:
                s.br_sl.setValue(b['value'])
            s.br_val.setText(f"{b['value']}%" if ok else 'недоступна')
        if 'power' in ch:
            s._apply_power(st.get('power', {}))
        if 'winmode' in ch:
            s._apply_mode(st.get('winmode', {}))
        if 'wifi_need_password' in ch and st.get('wifi_need_password'):
            ssid = st['wifi_need_password']
            st['wifi_need_password'] = ''
            pwd, ok = QInputDialog.getText(None, 'Wi-Fi', f'Пароль сети «{ssid}»:', QLineEdit.Password)
            if ok and pwd:
                s.hub.wifi_connect(ssid, pwd)

    def _apply_audio(s, a):
        out = a.get('out', {})
        v = out.get('volume')
        s.vol_sl.setEnabled(v is not None)
        if v is not None and not s.vol_sl.drag:
            s.vol_sl.setValue(v)
        s.vol_val.setText('—' if v is None else ('Без звука' if out.get('muted') else f'{v}%'))
        s.vol_mute.setText('🔇' if out.get('muted') else '🔊')
        cur = next((d for d in out.get('devices', []) if d['default']), None)
        s.vol_dev.setText(QFontMetrics(s.vol_dev.font()).elidedText(cur['name'] if cur else 'Нет устройства вывода', Qt.ElideRight, 190) + ' ▾')
        s._apply_mic()

        def dev_update(r, d):
            r.data = d
            r.set(d['name'], 'Используется' if d['default'] else '', checked=d['default'])
        for key, rows, hint in (('out', s.out_rows, s.out_hint), ('in', s.in_rows, s.in_hint)):
            devs = a.get(key, {}).get('devices', [])
            hint.setVisible(not devs)
            rows.sync([(d['id'], d) for d in devs], dev_update, at=s.pg_audio.body.indexOf(hint) + 1)
        apps = a.get('sessions', [])
        s.app_hint.setVisible(not apps)
        s.app_rows.sync([(x['name'], x) for x in apps], lambda w, d: w.apply(d), at=s.pg_audio.body.indexOf(s.app_hint) + 1)

    def _apply_wifi(s, st):
        w = st.get('wifi', {})
        if not w.get('present'):
            s.t_wifi.set_state(False, 'Нет адаптера', False)
        elif not w.get('on'):
            s.t_wifi.set_state(False, 'Выключен')
        elif w.get('connected'):
            s.t_wifi.set_state(True, w.get('ssid', ''))
        else:
            s.t_wifi.set_state(True, 'Нет подключения')
        s._silent(s.wifi_tg, bool(w.get('on')))
        s.wifi_tg.setEnabled(bool(w.get('present')))
        cur = w.get('ssid', '')
        nets = st.get('wifi_networks', []) if w.get('on') else []
        s.wifi_hint.setText('Wi-Fi адаптер не найден' if not w.get('present') else
                            ('Wi-Fi выключен' if not w.get('on') else ('' if nets else 'Ищу сети… (нажмите «Обновить»)')))
        s.wifi_hint.setVisible(bool(s.wifi_hint.text()))

        def upd(r, d):
            conn = d['ssid'] == cur and bool(cur)
            r.data = dict(d, connected=conn)
            r.set(d['ssid'], 'Подключено' if conn else ('Защищённая сеть' if d['secured'] else 'Открытая сеть'),
                  right='▂▄▆█'[:max(1, min(4, d['bars']))] if d['bars'] else '▁', checked=conn)
        s.wifi_rows.sync([(n['ssid'], n) for n in nets], upd, at=s.pg_wifi.body.indexOf(s.wifi_hint) + 1)

    def _apply_bt(s, b):
        if not b.get('present'):
            s.t_bt.set_state(False, 'Нет адаптера', False)
        elif not b.get('on'):
            s.t_bt.set_state(False, 'Выключен')
        else:
            n = sum(1 for d in b.get('devices', []) if d['connected'])
            s.t_bt.set_state(True, f'Подключено: {n}' if n else 'Нет подключённых')
        s._silent(s.bt_tg, bool(b.get('on')))
        s.bt_tg.setEnabled(bool(b.get('present')))
        devs = b.get('devices', []) if b.get('on') else []
        s.bt_hint.setText('Bluetooth-адаптер не найден' if not b.get('present') else
                          ('Bluetooth выключен' if not b.get('on') else ('' if devs else 'Нет сопряжённых устройств — добавьте через «Добавить устройство»')))
        s.bt_hint.setVisible(bool(s.bt_hint.text()))

        def upd(r, d):
            r.data = d
            r.set(d['name'], 'Подключено — нажмите, чтобы отключить' if d['connected'] else 'Сопряжено — нажмите, чтобы подключить',
                  dot=GREEN if d['connected'] else QColor(150, 150, 155))
        s.bt_rows.sync([(d['id'], d) for d in devs], upd, at=s.pg_bt.body.indexOf(s.bt_hint) + 1)

    def _apply_power(s, p):
        bat, mode, saver = p.get('battery'), p.get('mode'), p.get('saver')
        names = {'efficiency': 'энергосбережение', 'balanced': 'баланс', 'performance': 'производительность'}
        parts = []
        if bat is not None:
            parts.append(f"{bat}%" + (' · заряжается' if p.get('plugged') else ''))
        if mode:
            parts.append(names[mode])
        if saver:
            parts.append('экономия заряда Windows')
        on = mode == 'efficiency' or bool(saver)
        s.t_pow.set_state(on, ' · '.join(parts) or 'Режим питания недоступен', bool(p))
        s.pw_info.setText((f"Заряд: {bat}%" + (' (подключено к сети)' if p.get('plugged') else '') + '. ' if bat is not None else 'Батареи нет. ')
                          + ('Включена экономия заряда Windows. ' if saver else '')
                          + ('' if mode else 'Режимы питания на этом устройстве недоступны.'))
        for key, (r, title, sub) in s.pw_rows.items():
            r.set(title, sub, checked=(mode == key))
            r.setEnabled(mode is not None)

    def _apply_mode(s, wm):
        if not wm:
            s.t_mode.set_state(False, 'Недоступно', False)
            return
        sd, ad = not wm['system_light'], not wm['apps_light']
        s.t_mode.set_state(sd or ad, 'Тёмный' if sd and ad else ('Светлый' if not sd and not ad else 'Смешанный'))
        s._silent(s.mode_tg['system'], sd)
        s._silent(s.mode_tg['apps'], ad)
