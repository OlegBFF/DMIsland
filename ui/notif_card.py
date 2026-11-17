"""Карточка уведомления на острове и строка истории уведомлений."""
import hashlib
import math
import time
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import QLineEdit, QWidget
from core.notif_rules import PRIORITY_NAMES, format_time
from ui.icons import VectorIcon
from ui.themes import STYLE
from ui.widgets import fnt

PRIO_COL = {'important': QColor('#ff453a'), 'system': QColor('#0a84ff'), 'normal': QColor('#8e8e93')}
CARD_W = 480          # ширина острова в режиме карточки


def clamp01(v):
    return max(0.0, min(1.0, v))


def fg_col():
    return QColor('#141416') if STYLE['light'] else QColor('white')


def muted_col(a=150):
    return QColor(20, 20, 22, a) if STYLE['light'] else QColor(255, 255, 255, a)


def avatar_color(name: str) -> QColor:
    return QColor.fromHsv(int(hashlib.md5((name or '?').encode('utf-8')).hexdigest()[:4], 16) % 360, 150, 205)


def initials(name: str) -> str:
    words = [w for w in (name or '').replace('_', ' ').split() if w[:1].isalnum()]
    return ((words[0][:1] + (words[1][:1] if len(words) > 1 else '')) if words else '?').upper()


def draw_avatar(p: QPainter, r: QRectF, n: dict, icons: dict):
    """Аватар отправителя (цветной круг с инициалами) со значком приложения в углу; если отправитель = приложение —
    просто логотип. Кольцо вокруг аватара — цвет важности (красное у важных)."""
    pm = icons.get(n.get('app_id'))
    has_pm = isinstance(pm, QPixmap) and not pm.isNull()
    sender = (n.get('title') or '').strip()
    app = (n.get('app') or '').strip()
    person = bool(sender) and sender.casefold() != app.casefold() and len(sender) <= 40 and n.get('source') != 'island'
    p.save()
    if person:
        base = avatar_color(sender)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, base.lighter(118))
        g.setColorAt(1, base.darker(112))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(r)
        p.setPen(QColor('white'))
        p.setFont(fnt(r.width() * 0.38, QFont.DemiBold))
        p.drawText(r, Qt.AlignCenter, initials(sender))
        d = r.width() * 0.46                                   # значок приложения в правом нижнем углу
        b = QRectF(r.right() - d * 0.82, r.bottom() - d * 0.82, d, d)
        p.setBrush(QColor(STYLE['th']['base']))
        p.drawEllipse(b.adjusted(-2, -2, 2, 2))
        bp = QPainterPath()
        bp.addRoundedRect(b, d * 0.3, d * 0.3)
        p.setClipPath(bp)
        if has_pm:
            p.fillRect(b, QColor(255, 255, 255, 240) if not STYLE['light'] else QColor(0, 0, 0, 20))
            p.drawPixmap(b.adjusted(d * .1, d * .1, -d * .1, -d * .1).toRect(), pm)
        else:
            p.fillRect(b, avatar_color(app or sender))
            p.setPen(QColor('white'))
            p.setFont(fnt(d * 0.5, QFont.DemiBold))
            p.drawText(b, Qt.AlignCenter, (app[:1] or '?').upper())
        p.setClipping(False)
    else:
        path = QPainterPath()
        path.addRoundedRect(r, r.width() * 0.28, r.width() * 0.28)
        p.setClipPath(path)
        if has_pm:
            p.fillRect(r, QColor(255, 255, 255, 235) if not STYLE['light'] else QColor(0, 0, 0, 14))
            side = r.width() * 0.82
            p.drawPixmap(QRectF(r.center().x() - side / 2, r.center().y() - side / 2, side, side).toRect(), pm)
        else:
            p.fillRect(r, avatar_color(app or sender))
            p.setPen(QColor('white'))
            p.setFont(fnt(r.width() * 0.42, QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, ((app or sender or '?')[:1]).upper())
        p.setClipping(False)
    prio = n.get('priority')
    if prio in ('important', 'system'):
        ring = QColor(PRIO_COL[prio])
        ring.setAlpha(230 if prio == 'important' else 150)
        p.setPen(QPen(ring, 1.8))
        p.setBrush(Qt.NoBrush)
        rr = r.adjusted(-2.5, -2.5, 2.5, 2.5)
        if person:
            p.drawEllipse(rr)
        else:
            p.drawRoundedRect(rr, r.width() * 0.3, r.width() * 0.3)
    p.restore()


def wrapped_height(text: str, font: QFont, width: int, max_lines: int) -> int:
    fm = QFontMetrics(font)
    h = fm.boundingRect(QRect(0, 0, max(width, 40), 2000), Qt.TextWordWrap, text or ' ').height()
    return min(h, fm.lineSpacing() * max_lines)


QUICK_REPLIES = ('Ок', 'Спасибо', 'Позже отвечу', 'Да', 'Нет')
ACT_ICONS = {'copy_code': 'copy', 'copy_phone': 'copy', 'link': 'link', 'preview_url': 'image'}


class NotifCard(QWidget):
    """Содержимое расширенного острова: приложение, отправитель, текст, превью, действия, быстрый ответ, очередь."""
    replied = Signal(dict, str)
    snoozeRequested = Signal(dict)
    openRequested = Signal(dict)
    dismissed = Signal(dict)
    readRequested = Signal(dict)
    navigated = Signal(int)
    historyRequested = Signal()
    actionRequested = Signal(dict, str, object)     # (уведомление, ключ действия, аргумент)
    draftRequested = Signal(dict)                   # «ИИ, предложи ответ»
    imageRequested = Signal(dict, int)              # открыть превью с номером

    def __init__(s, host):
        super().__init__(host)
        s.host = host
        s.items, s.idx, s.icons = [], 0, {}
        s.reply_info = lambda n: None           # n -> подсказка для поля ответа, если ответить можно
        s.smart_actions = lambda n: []          # n -> [{'key','label','arg'}] — ссылки, коды, музыка
        s.previews = {}                         # id уведомления -> [QPixmap]
        s.playing = lambda: False
        s.t0, s.fade, s.progress = time.time(), 0.0, None
        s.replying, s.hover, s.drafting = False, '', False
        s._light = None
        s.setMouseTracking(True)
        s.setCursor(Qt.ArrowCursor)
        s.ed = QLineEdit(s)
        s.ed.hide()
        s.ed.returnPressed.connect(s._send)
        sc = QShortcut(QKeySequence(Qt.Key_Escape), s.ed)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(s.cancel_reply)
        s.hide()

    # ---------- данные ----------
    def cur(s):
        return s.items[s.idx] if 0 <= s.idx < len(s.items) else None

    def set_items(s, items, idx=0):
        changed = (s.cur() or {}).get('id') != (items[idx]['id'] if items else None)
        s.items, s.idx = list(items), max(0, min(idx, len(items) - 1))
        if changed:
            s.t0 = time.time()
            s.cancel_reply(silent=True)
        s.restyle()

    def same_app_count(s) -> int:
        n = s.cur()
        if not n:
            return 0
        key = (n.get('app_id') or n.get('app') or '').casefold()
        return sum(1 for x in s.items if (x.get('app_id') or x.get('app') or '').casefold() == key)

    def preferred_height(s) -> int:
        return int(s._layout(CARD_W - 36)['height'])

    def restyle(s):
        if s._light == STYLE['light']:
            return
        s._light = STYLE['light']
        bg, bd, col = ('rgba(0,0,0,0.07)', 'rgba(0,0,0,0.16)', '#141416') if STYLE['light'] else ('rgba(255,255,255,0.10)', 'rgba(255,255,255,0.16)', 'white')
        s.ed.setStyleSheet(f"QLineEdit{{background:{bg};border:1px solid {bd};border-radius:12px;padding:0 12px;color:{col};font-size:12px}}"
                           f"QLineEdit:focus{{border:1px solid {STYLE['acc'].name()}}}")

    # ---------- раскладка ----------
    def _layout(s, w=None):
        w = w or s.width()
        n = s.cur()
        bh = wrapped_height(n['body'], fnt(10.5), w, 3) if n and n.get('body') else 0
        y_title = 46.0
        y_body = y_title + 24
        y = y_body + (bh + 4 if bh else 0) + 8
        L = {'avatar': QRectF(0, 3, 34, 34), 'title': QRectF(0, y_title, w, 22), 'body': QRectF(0, y_body, w, bh),
             'close': QRectF(w - 28, 6, 26, 26), 'next': QRectF(w - 56, 6, 26, 26),
             'prev': QRectF(w - 108, 6, 26, 26), 'count': QRectF(w - 82, 6, 26, 26), 'hist': QRectF(w - 28 - 30, 6, 26, 26),
             'previews': [], 'chips': [], 'quick': [], 'acts': []}
        pms = s.previews.get(n['id'], []) if n else []
        if pms:
            x = 0.0
            for i, pm in enumerate(pms[:3]):
                r = QRectF(x, y, 112, 84)
                L['previews'].append((i, r))
                x += 118
            y += 92
        if s.replying:
            x = 0.0
            fm = QFontMetrics(fnt(9.4, QFont.DemiBold))
            for i, t in enumerate(QUICK_REPLIES):
                cw = fm.horizontalAdvance(t) + 22
                if x + cw > w:
                    break
                L['quick'].append((f'q{i}', t, QRectF(x, y, cw, 28)))
                x += cw + 6
            y += 34
            L['edit'] = QRectF(0, y, w - 146, 34)
            L['btns'] = [('ai', QRectF(w - 140, y, 34, 34)), ('send', QRectF(w - 100, y, 70, 34)), ('cancel', QRectF(w - 26, y, 26, 34))]
            y += 34
        else:
            smart = s.smart_actions(n) if n else []
            if smart:
                x, fm = 0.0, QFontMetrics(fnt(9.4, QFont.DemiBold))
                for i, a in enumerate(smart):
                    if a['key'] == 'music':
                        for j, k in enumerate(('prev', 'toggle', 'next')):
                            L['chips'].append((f'music:{k}', a, QRectF(x, y, 38, 30)))
                            x += 42
                        continue
                    cw = min(fm.horizontalAdvance(a['label']) + 44, 200)
                    if x + cw > w:
                        break
                    L['chips'].append((f'act:{i}', a, QRectF(x, y, cw, 30)))
                    x += cw + 6
                y += 38
            acts = []
            if n:
                if s.reply_info(n) is not None:
                    acts.append(('reply', 'Ответить'))
                acts += [('snooze', 'Отложить'), ('open', 'Открыть'), ('read', 'Прочитано')]
            gap = 8
            bw = (w - gap * (len(acts) - 1)) / max(len(acts), 1)
            L['btns'] = [(k, QRectF(i * (bw + gap), y, bw, 34)) for i, (k, _) in enumerate(acts)]
            L['labels'] = dict(acts)
            y += 34
        L['nav'] = len(s.items) > 1
        L['height'] = y + 18
        return L

    def resizeEvent(s, e):
        s._place_editor()

    def _place_editor(s):
        if s.replying:
            s.ed.setGeometry(s._layout()['edit'].toRect())

    # ---------- ответ ----------
    def start_reply(s):
        n = s.cur()
        hint = s.reply_info(n) if n else None
        if hint is None:
            return
        s.replying = True
        s.ed.setPlaceholderText(hint)
        s.ed.clear()
        s._place_editor()
        s.ed.show()
        s.host.set_typing(True)
        s.ed.setFocus()
        s.update()

    def cancel_reply(s, silent=False):
        if not s.replying:
            return
        s.replying = False
        s.drafting = False
        s.ed.hide()
        if not silent:
            s.update()

    def set_draft(s, text):
        s.drafting = False
        if s.replying and text:
            s.ed.setText(text)
            s.ed.setFocus()
        s.update()

    def _send(s):
        n, text = s.cur(), s.ed.text().strip()
        if n and text:
            s.replied.emit(n, text)

    # ---------- мышь ----------
    def _hit(s, pos):
        L = s._layout()
        for key in ('close', 'next', 'prev', 'hist'):
            if key in ('next', 'prev') and not L['nav']:
                continue
            if L[key].contains(pos):
                return key
        for k, r in L['btns']:
            if r.contains(pos):
                return k
        for k, _, r in L['chips']:
            if r.contains(pos):
                return k
        for k, _, r in L['quick']:
            if r.contains(pos):
                return k
        for i, r in L['previews']:
            if r.contains(pos):
                return f'img:{i}'
        return ''

    def mouseMoveEvent(s, e):
        h = s._hit(e.position())
        if h != s.hover:
            s.hover = h
            s.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            s.update()

    def leaveEvent(s, e):
        s.hover = ''
        s.update()

    def mousePressEvent(s, e):
        n = s.cur()
        if e.button() != Qt.LeftButton or not n:
            return
        h = s._hit(e.position())
        if h == 'close':
            s.dismissed.emit(n)
        elif h == 'next':
            s.navigated.emit(1)
        elif h == 'prev':
            s.navigated.emit(-1)
        elif h == 'hist':
            s.historyRequested.emit()
        elif h == 'reply':
            s.start_reply()
        elif h == 'snooze':
            s.snoozeRequested.emit(n)
        elif h == 'open':
            s.openRequested.emit(n)
        elif h == 'read':
            s.readRequested.emit(n)
        elif h == 'send':
            s._send()
        elif h == 'cancel':
            s.cancel_reply()
        elif h == 'ai':
            s.drafting = True
            s.update()
            s.draftRequested.emit(n)
        elif h.startswith('q') and h[1:].isdigit():
            t = QUICK_REPLIES[int(h[1:])]
            s.ed.setText(t)
            s.ed.setFocus()
        elif h.startswith('img:'):
            s.imageRequested.emit(n, int(h[4:]))
        elif h.startswith('music:'):
            s.actionRequested.emit(n, 'music', h[6:])
        elif h.startswith('act:'):
            a = s.smart_actions(n)[int(h[4:])]
            s.actionRequested.emit(n, a['key'], a.get('arg'))

    # ---------- рисование ----------
    def _pill(s, p, r, text, key, primary=False, icon=None):
        hv = s.hover == key
        p.setPen(Qt.NoPen)
        if primary:
            c = QColor(STYLE['acc'])
            c.setAlpha(230 if hv else 190)
            p.setBrush(c)
        else:
            p.setBrush(QColor(255, 255, 255, 40 if hv else 22) if not STYLE['light'] else QColor(0, 0, 0, 26 if hv else 14))
        p.drawRoundedRect(r.adjusted(0, 1, 0, -1), 12, 12)
        fg = QColor('white') if primary else fg_col()
        if icon:
            VectorIcon.draw(p, icon, QRectF(r.x() + 10, r.center().y() - 8, 16, 16), fg)
            p.setPen(fg)
            p.setFont(fnt(9.4, QFont.DemiBold))
            p.drawText(QRectF(r.x() + 30, r.y(), r.width() - 36, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(p.font()).elidedText(text, Qt.ElideRight, int(r.width() - 38)))
        else:
            p.setPen(fg)
            p.setFont(fnt(9.6, QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, text)

    def paintEvent(s, e):
        n = s.cur()
        if not n or s.fade < 0.01:
            return
        s.restyle()
        now = time.time()
        age = now - s.t0
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        L = s._layout()
        w = s.width()
        col = PRIO_COL.get(n['priority'], PRIO_COL['normal'])
        appear = clamp01(age * 5.5)
        p.setOpacity(s.fade * appear)
        slide = 14.0 * math.exp(-age * 8.0)
        p.translate(0, slide)

        # аватар с пружинным «попом»
        pop = 1.0 + 0.22 * math.exp(-age * 7.0) * math.cos(age * 15.0)
        ar = L['avatar']
        p.save()
        p.translate(ar.center())
        p.scale(pop, pop)
        p.translate(-ar.center().x(), -ar.center().y())
        draw_avatar(p, ar, n, s.icons)
        p.restore()

        # приложение · время  +  чип приоритета
        x = 44.0
        p.setPen(muted_col(190))
        p.setFont(fnt(9.3, QFont.DemiBold))
        app = QFontMetrics(p.font()).elidedText(n.get('app') or 'Уведомление', Qt.ElideRight, 170)
        p.drawText(QRectF(x, 2, 180, 18), Qt.AlignVCenter | Qt.AlignLeft, app)
        p.setPen(muted_col(120))
        p.setFont(fnt(8.8))
        same = s.same_app_count()
        extra = f"  ·  ×{n['count']}" if n.get('count', 1) > 1 else ''
        extra += f"  ·  в группе: {same}" if same > 1 else ''
        p.drawText(QRectF(x, 21, 230, 16), Qt.AlignVCenter | Qt.AlignLeft, format_time(n['created'], now) + extra)
        chip = PRIORITY_NAMES.get(n['priority'], '')
        cf = fnt(8.4, QFont.DemiBold)
        cw = QFontMetrics(cf).horizontalAdvance(chip) + 16
        cx = 44 + 176
        cr = QRectF(cx, 2, cw, 18)
        pulse = 0.5 + 0.5 * math.sin(now * 3.2) if n['priority'] == 'important' else 0.0
        bg = QColor(col)
        bg.setAlpha(int(46 + 38 * pulse))
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(cr, 10, 10)
        p.setPen(col.lighter(125) if not STYLE['light'] else col.darker(130))
        p.setFont(cf)
        p.drawText(cr, Qt.AlignCenter, chip)

        # навигация и закрытие
        def icon_btn(key, rect, draw):
            if s.hover == key:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 30) if not STYLE['light'] else QColor(0, 0, 0, 22))
                p.drawRoundedRect(rect, 9, 9)
            draw(rect)
        icon_btn('close', L['close'], lambda r: VectorIcon.draw(p, 'close', r.adjusted(5, 5, -5, -5), muted_col(200)))
        if L['nav']:
            p.setPen(muted_col(200))
            p.setFont(fnt(14, QFont.DemiBold))
            icon_btn('prev', L['prev'], lambda r: p.drawText(r, Qt.AlignCenter, '‹'))
            icon_btn('next', L['next'], lambda r: p.drawText(r, Qt.AlignCenter, '›'))
            p.setFont(fnt(8.8))
            p.setPen(muted_col(150))
            p.drawText(L['count'], Qt.AlignCenter, f"{s.idx + 1}/{len(s.items)}")

        # заголовок (отправитель) и текст
        p.setPen(fg_col())
        p.setFont(fnt(12.5, QFont.DemiBold))
        p.drawText(L['title'].translated(slide * 0.3, 0), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(n.get('title') or n.get('app') or '', Qt.ElideRight, w - 8))
        if n.get('body'):
            p.setPen(muted_col(210))
            p.setFont(fnt(10.5))
            p.drawText(L['body'].translated(slide * 0.5, 0), Qt.TextWordWrap | Qt.AlignTop | Qt.AlignLeft, n['body'])

        # превью картинок
        pms = s.previews.get(n['id'], [])
        for i, r in L['previews']:
            pm = pms[i]
            path = QPainterPath()
            path.addRoundedRect(r, 12, 12)
            p.save()
            p.setClipPath(path)
            sc = pm.scaled(r.size().toSize(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap(int(r.x() - (sc.width() - r.width()) / 2), int(r.y() - (sc.height() - r.height()) / 2), sc)
            if s.hover == f'img:{i}':
                p.fillRect(r, QColor(255, 255, 255, 36))
            p.restore()
            p.setPen(QPen(QColor(255, 255, 255, 50) if not STYLE['light'] else QColor(0, 0, 0, 40), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 12, 12)

        # быстрые ответы
        for k, t, r in L['quick']:
            hv = s.hover == k
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 38 if hv else 20) if not STYLE['light'] else QColor(0, 0, 0, 24 if hv else 12))
            p.drawRoundedRect(r, 14, 14)
            p.setPen(fg_col())
            p.setFont(fnt(9.4, QFont.DemiBold))
            p.drawText(r, Qt.AlignCenter, t)

        # действия из содержимого и управление музыкой
        for k, a, r in L['chips']:
            if k.startswith('music:'):
                what = k[6:]
                hv = s.hover == k
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 40 if hv else 22) if not STYLE['light'] else QColor(0, 0, 0, 26 if hv else 14))
                p.drawRoundedRect(r.adjusted(0, 1, 0, -1), 15, 15)
                ic = 'prev' if what == 'prev' else ('next' if what == 'next' else ('pause' if s.playing() else 'play'))
                VectorIcon.draw(p, ic, QRectF(r.center().x() - 10, r.center().y() - 10, 20, 20), fg_col())
            else:
                s._pill(p, r, a['label'], k, icon=ACT_ICONS.get(a['key']))

        # кнопки: ответ или основные действия
        if s.replying:
            for k, r in L['btns']:
                hv = s.hover == k
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(STYLE['acc']) if k == 'send' else (QColor(255, 255, 255, 40 if hv else 22) if not STYLE['light'] else QColor(0, 0, 0, 28 if hv else 14)))
                p.drawRoundedRect(r.adjusted(0, 1, 0, -1), 12, 12)
                p.setPen(QColor('white') if k == 'send' else muted_col(220))
                p.setFont(fnt(9.6, QFont.DemiBold))
                if k == 'ai':
                    VectorIcon.draw(p, 'spark', QRectF(r.center().x() - 9, r.center().y() - 9, 18, 18), fg_col() if not s.drafting else QColor(STYLE['acc']))
                else:
                    p.drawText(r, Qt.AlignCenter, 'Отправить' if k == 'send' else '✕')
        else:
            for k, r in L['btns']:
                s._pill(p, r, L['labels'][k], k, primary=(k == 'reply'))

        # оставшееся время показа
        if s.progress is not None and not s.replying:
            p.setPen(Qt.NoPen)
            c = QColor(col)
            c.setAlpha(190)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(0, s.height() - 8, (w) * clamp01(s.progress), 2.4), 1.2, 1.2)


class NotifRow(QWidget):
    """Строка истории: приоритет, приложение, отправитель, текст; при наведении — отложить и удалить."""
    clicked = Signal(dict)
    snoozeClicked = Signal(dict)
    deleteClicked = Signal(dict)
    contextRequested = Signal(dict, QPointF)

    def __init__(s, icons):
        super().__init__()
        s.n, s.icons, s.hover = None, icons, ''
        s.setFixedHeight(64)
        s.setMouseTracking(True)
        s.setCursor(Qt.PointingHandCursor)

    def set_data(s, n):
        s.n = n
        s.update()

    def _btns(s):
        w = s.width()
        return {'snooze': QRectF(w - 62, 8, 24, 24), 'delete': QRectF(w - 34, 8, 24, 24)}

    def _hit(s, pos):
        for k, r in s._btns().items():
            if r.contains(pos):
                return k
        return ''

    def enterEvent(s, e):
        s.update()

    def leaveEvent(s, e):
        s.hover = ''
        s.update()

    def mouseMoveEvent(s, e):
        h = s._hit(e.position()) if s.underMouse() else ''
        if h != s.hover:
            s.hover = h
            s.update()

    def mousePressEvent(s, e):
        if not s.n:
            return
        if e.button() == Qt.RightButton:
            s.contextRequested.emit(s.n, e.globalPosition())
            return
        h = s._hit(e.position())
        if h == 'snooze':
            s.snoozeClicked.emit(s.n)
        elif h == 'delete':
            s.deleteClicked.emit(s.n)
        else:
            s.clicked.emit(s.n)

    def paintEvent(s, e):
        n = s.n
        if not n:
            return
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = s.width(), s.height()
        unread = not n['read']
        col = PRIO_COL.get(n['priority'], PRIO_COL['normal'])
        if s.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 18) if not STYLE['light'] else QColor(0, 0, 0, 12))
            p.drawRoundedRect(QRectF(0, 1, w, h - 2), 12, 12)
        bar = QColor(col)
        bar.setAlpha(255 if unread else 80)
        p.setPen(Qt.NoPen)
        p.setBrush(bar)
        p.drawRoundedRect(QRectF(4, 14, 3.2, h - 28), 1.6, 1.6)
        draw_avatar(p, QRectF(16, 16, 32, 32), n, s.icons)
        x, tw = 60, w - 60 - 80
        p.setPen(muted_col(170))
        p.setFont(fnt(8.8))
        meta = f"{n.get('app') or 'Уведомление'}  ·  {format_time(n['created'], time.time())}" + (f"  ·  ×{n['count']}" if n.get('count', 1) > 1 else '')
        p.drawText(QRectF(x, 6, tw, 16), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(meta, Qt.ElideRight, int(tw)))
        p.setPen(fg_col())
        f = fnt(10.5, QFont.Bold if unread else QFont.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(x, 22, tw, 18), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(f).elidedText(n.get('title') or '', Qt.ElideRight, int(tw)))
        p.setPen(muted_col(200 if unread else 130))
        p.setFont(fnt(9.6))
        body = (n.get('body') or '').replace('\n', ' ')
        p.drawText(QRectF(x, 40, tw + 10, 18), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(body, Qt.ElideRight, int(tw + 10)))
        if n.get('snooze_until') and n['snooze_until'] > time.time():
            p.setPen(col)
            p.setFont(fnt(8.8, QFont.DemiBold))
            p.drawText(QRectF(w - 150, 8, 140, 18), Qt.AlignVCenter | Qt.AlignRight, 'отложено до ' + time.strftime('%H:%M', time.localtime(n['snooze_until'])))
        elif s.underMouse():
            for k, r in s._btns().items():
                if s.hover == k:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(255, 255, 255, 34) if not STYLE['light'] else QColor(0, 0, 0, 24))
                    p.drawRoundedRect(r, 8, 8)
                VectorIcon.draw(p, 'bell' if k == 'snooze' else 'close', r.adjusted(5, 5, -5, -5), muted_col(220))
        elif unread:
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(w - 18, 18), 4.5, 4.5)


class NotifGroupHeader(QWidget):
    """Заголовок группы «по приложениям»: логотип, название, счётчики, последнее сообщение; наведение — «прочитано» и «очистить»."""
    toggled = Signal(str)
    readClicked = Signal(str)
    clearClicked = Signal(str)

    def __init__(s, icons):
        super().__init__()
        s.g, s.icons, s.hover, s.collapsed = None, icons, '', False
        s.setFixedHeight(58)
        s.setMouseTracking(True)
        s.setCursor(Qt.PointingHandCursor)

    def set_data(s, key, app, items, summary, collapsed):
        s.g = {'key': key, 'app': app, 'items': items, 'sum': summary}
        s.collapsed = collapsed
        s.update()

    def _btns(s):
        w = s.width()
        return {'read': QRectF(w - 62, 17, 24, 24), 'clear': QRectF(w - 34, 17, 24, 24)}

    def _hit(s, pos):
        for k, r in s._btns().items():
            if r.contains(pos):
                return k
        return ''

    def enterEvent(s, e):
        s.update()

    def leaveEvent(s, e):
        s.hover = ''
        s.update()

    def mouseMoveEvent(s, e):
        h = s._hit(e.position()) if s.underMouse() else ''
        if h != s.hover:
            s.hover = h
            s.update()

    def mousePressEvent(s, e):
        if not s.g:
            return
        h = s._hit(e.position())
        if h == 'read':
            s.readClicked.emit(s.g['key'])
        elif h == 'clear':
            s.clearClicked.emit(s.g['key'])
        else:
            s.toggled.emit(s.g['key'])

    def paintEvent(s, e):
        if not s.g:
            return
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = s.width(), s.height()
        items, sm = s.g['items'], s.g['sum']
        col = PRIO_COL.get(sm['priority'], PRIO_COL['normal'])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 22 if s.underMouse() else 12) if not STYLE['light'] else QColor(0, 0, 0, 16 if s.underMouse() else 9))
        p.drawRoundedRect(QRectF(0, 2, w, h - 4), 14, 14)
        first = items[0]
        draw_avatar(p, QRectF(12, 13, 32, 32), first, s.icons)
        x, tw = 56, w - 56 - 76
        p.setPen(fg_col())
        p.setFont(fnt(10.8, QFont.Bold))
        p.drawText(QRectF(x, 8, tw, 20), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(s.g['app'], Qt.ElideRight, int(tw - 70)))
        nm = QFontMetrics(p.font()).horizontalAdvance(s.g['app'])
        cnt = f"{sm['total']}" + (f" · новых {sm['unread']}" if sm['unread'] else '')
        p.setPen(col if sm['unread'] else muted_col(150))
        p.setFont(fnt(9, QFont.DemiBold))
        p.drawText(QRectF(x + min(nm, tw - 70) + 8, 8, 120, 20), Qt.AlignVCenter | Qt.AlignLeft, cnt)
        p.setPen(muted_col(150))
        p.setFont(fnt(9.4))
        last = ((first.get('title') or '') + ('  ' + (first.get('body') or '').replace('\n', ' ') if first.get('body') else '')).strip()
        p.drawText(QRectF(x, 29, tw, 18), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(last, Qt.ElideRight, int(tw)))
        if s.underMouse():
            for k, r in s._btns().items():
                if s.hover == k:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(255, 255, 255, 34) if not STYLE['light'] else QColor(0, 0, 0, 24))
                    p.drawRoundedRect(r, 8, 8)
                VectorIcon.draw(p, 'check' if k == 'read' else 'close', r.adjusted(5, 5, -5, -5), muted_col(220))
        else:
            ch = QPainterPath()                          # стрелка раскрытия
            cx, cy = w - 24, h / 2
            d = 4 if not s.collapsed else -4
            ch.moveTo(cx - 5, cy - d / 2)
            ch.lineTo(cx, cy + d / 2)
            ch.lineTo(cx + 5, cy - d / 2)
            p.setPen(QPen(muted_col(170), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(ch)
