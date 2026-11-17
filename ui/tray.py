"""Иконка и меню в системном трее."""
import os
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from core.config import save_cfg
from core.constants import APP_NAME, SHOTS_DIR
from core.win32 import autostart_enabled, set_autostart
from ui.animations import ANIM_STYLES
from ui.icons import dot_icon, vicon
from ui.settings_dialog import SettingsDialog
from ui.themes import STYLE, THEMES, menu_qss


class TrayMixin:
    """Часть класса Island: TrayMixin."""

    # ==================== ТРЕЙ ====================
    def make_tray_icon(s) -> QIcon:
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        th = STYLE['th']
        gr = QLinearGradient(0, 17, 0, 47)
        gr.setColorAt(0, QColor(th['base']).lighter(160))
        gr.setColorAt(1, QColor(th['base2']).lighter(130))
        p.setPen(QPen(QColor(s.acc), 3.4))
        p.setBrush(gr)
        p.drawRoundedRect(QRectF(3, 17, 58, 30), 15, 15)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(s.acc))
        p.drawEllipse(QPointF(19, 32), 6.5, 6.5)
        p.setBrush(QColor('#141416') if STYLE['light'] else QColor(255, 255, 255, 235))
        for i, bh in enumerate((9, 15, 11)):
            p.drawRoundedRect(QRectF(34 + i * 7, 32 - bh / 2, 4, bh), 2, 2)
        p.end()
        return QIcon(pm)

    def mk_menu(s, parent=None, title='') -> QMenu:
        m = QMenu(title, parent)
        m.setWindowFlags(m.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        m.setAttribute(Qt.WA_TranslucentBackground)
        m.setStyleSheet(menu_qss())
        if parent is not None and parent is not s:
            s._sub_menus.append(m)          # подменю пересоздаются при каждом открытии — старые удаляем
        return m

    def setup_tray(s):
        s.tray = QSystemTrayIcon(s.make_tray_icon(), s)
        s.tray.setToolTip(APP_NAME)
        s.menu = s.mk_menu()
        s.menu.aboutToShow.connect(s.rebuild_tray_menu)
        s.tray.setContextMenu(s.menu)
        s.tray.activated.connect(s.on_tray_activated)
        s.tray.show()

    def on_tray_activated(s, reason):
        R = QSystemTrayIcon.ActivationReason
        if reason == R.Trigger:
            s.toggle_open()
        elif reason == R.MiddleClick:
            s.media.cmd('try_toggle_play_pause_async')

    def rebuild_tray_menu(s):
        for x in s._sub_menus:
            x.deleteLater()
        s._sub_menus = []
        m = s.menu
        m.clear()
        m.setStyleSheet(menu_qss())
        fg = '#141416' if STYLE['light'] else '#f2f2f5'
        ic = lambda n: vicon(n, fg, 18)

        def add(menu, icon, text, fn=None, checked=None):
            a = menu.addAction(icon, text)
            if checked is not None:
                a.setCheckable(True)
                a.setChecked(bool(checked))
            if fn:
                a.triggered.connect(lambda _=False, f=fn: f())
            return a

        # Шапка: что сейчас играет
        fm = QFontMetrics(m.font())
        head = f"{s.mtitle} — {s.martist}" if (s.mtitle and s.martist) else (s.mtitle or APP_NAME)
        h = add(m, ic('music') if s.mtitle else ic('sun'), fm.elidedText(head, Qt.ElideRight, 230))
        h.setEnabled(False)
        s.tray.setToolTip(head if s.mtitle else APP_NAME)
        m.addSeparator()

        opened = s.mode == 'open' and s.tabs.pinned
        add(m, ic('home'), 'Свернуть остров' if opened else 'Открыть остров', s.toggle_open)
        add(m, ic('moon'), 'Скрыть остров', s.toggle_hidden, checked=s.user_hidden)

        # --- Оформление ---
        sub = s.mk_menu(m, 'Оформление')
        sub.setIcon(ic('palette'))
        cur = s.cfg.get('theme', 'obsidian')
        cur = 'obsidian' if cur == 'dark' else cur
        for key, th in THEMES.items():
            add(sub, dot_icon(th['acc']), th['name'], lambda k=key: s.set_cfg('theme', k), checked=(cur == key))
        add(sub, ic('monitor'), 'Как в Windows', lambda: s.set_cfg('theme', 'system'), checked=(cur == 'system'))
        sub.addSeparator()
        add(sub, ic('music'), 'Акцент из обложки трека',
            lambda: s.set_cfg('accent_mode', 'theme' if s.cfg.get('accent_mode') == 'cover' else 'cover'),
            checked=s.cfg.get('accent_mode') == 'cover')
        an = s.mk_menu(sub, 'Стиль анимации')
        an.setIcon(ic('spark'))
        for key, (_, _, name) in ANIM_STYLES.items():
            add(an, QIcon(), name, lambda k=key: s.set_cfg('anim_style', k), checked=s.cfg.get('anim_style', 'liquid') == key)
        sub.addMenu(an)
        m.addMenu(sub)

        # --- Плеер ---
        pl = s.mk_menu(m, 'Плеер')
        pl.setIcon(ic('play'))
        add(pl, ic('pause') if s.playing else ic('play'), 'Пауза' if s.playing else 'Воспроизвести',
            lambda: s.media.cmd('try_toggle_play_pause_async'))
        add(pl, ic('prev'), 'Предыдущий', lambda: s.media.cmd('try_skip_previous_async'))
        add(pl, ic('next'), 'Следующий', lambda: s.media.cmd('try_skip_next_async'))
        if len(s.players) > 1:
            pl.addSeparator()
            for r in s.players:
                add(pl, dot_icon(r['color']), r['name'], lambda k=r['key']: s.media.set_player(k),
                    checked=r['key'] == s.media.active_id)
            add(pl, ic('spark'), 'Авто · последний играющий', lambda: s.media.set_player(''), checked=not s.media.pinned)
        m.addMenu(pl)

        # --- Инструменты ---
        tl = s.mk_menu(m, 'Инструменты')
        tl.setIcon(ic('area'))
        for icn, name, fn in (('area', 'Скриншот области', lambda: s.snap('area')), ('full', 'Весь экран', s.full_shot),
                              ('ocr', 'Текст с экрана (OCR)', lambda: s.snap('ocr')), ('qr', 'Сканер QR', lambda: s.snap('qr')),
                              ('pick', 'Пипетка', lambda: s.snap('pick')), ('rec', 'Запись экрана', s.toggle_record),
                              ('cmd', 'Командная строка', s.open_command_palette)):
            add(tl, ic(icn), name, fn)
        m.addMenu(tl)

        # --- Поведение ---
        bh = s.mk_menu(m, 'Поведение')
        bh.setIcon(ic('sys'))
        add(bh, ic('pin'), 'Сквозной режим', lambda: s.toggle_cfg('click_through'), checked=s.cfg.get('click_through'))
        add(bh, ic('game'), 'Прятать в полноэкранных окнах',
            lambda: s.set_cfg('game_mode', 'off' if s.cfg.get('game_mode', 'hide') == 'hide' else 'hide'),
            checked=s.cfg.get('game_mode', 'hide') == 'hide')
        add(bh, ic('usb'), 'События устройств', lambda: s.toggle_cfg('device_events', True), checked=s.cfg.get('device_events', True))
        add(bh, ic('mic'), 'Индикаторы микрофона и камеры', lambda: s.toggle_cfg('privacy_dots', True),
            checked=s.cfg.get('privacy_dots', True))
        add(bh, ic('full'), 'Показывать на скриншотах', lambda: s.toggle_cfg('show_in_capture'), checked=s.cfg.get('show_in_capture'))
        m.addMenu(bh)

        m.addSeparator()
        add(m, ic('power'), 'Запускать с Windows', s.toggle_autostart, checked=autostart_enabled())
        add(m, ic('folder'), 'Папка скриншотов', lambda: (SHOTS_DIR.mkdir(parents=True, exist_ok=True), os.startfile(str(SHOTS_DIR))))
        add(m, ic('gear'), 'Настройки…', s.open_settings)
        m.addSeparator()
        add(m, ic('close'), 'Выход', QApplication.quit)

    def toggle_autostart(s):
        ok = set_autostart(not autostart_enabled())
        s.cfg['autostart'] = autostart_enabled()
        save_cfg(s.cfg)
        if not ok:
            s.pop('Автозапуск', 'Не удалось изменить реестр', (QColor('#ff453a'), 'close'))

    def open_settings(s):
        d = getattr(s, 'settings_dlg', None)
        if d is not None and d.isVisible():
            d.raise_()
            d.activateWindow()
            return
        s.settings_dlg = SettingsDialog(s)
        s.settings_dlg.show()
        s.settings_dlg.raise_()
        s.settings_dlg.activateWindow()
