"""Общие виджеты интерфейса: кнопки, ползунки, переключатели, карточки."""
from PySide6.QtCore import QEasingCurve, QMimeData, QPointF, QRectF, QSize, QVariantAnimation, Qt, Signal
from PySide6.QtGui import (
    QColor, QDrag, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QCheckBox, QPushButton, QToolButton, QWidget
from core.utils import clamp
from core.win32 import is_win_light
from ui.animations import Sp
from ui.icons import VectorIcon
from ui.themes import STYLE, THEMES, mix, on_acc


def fnt(pt, w=QFont.Normal):
    f = QFont()
    f.setFamilies(['Segoe UI Variable Display', 'Segoe UI'])
    f.setPointSizeF(pt)
    f.setWeight(w)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def rounded(pm, r):
    if pm.isNull():
        return pm
    o = QPixmap(pm.size())
    o.fill(Qt.transparent)
    p = QPainter(o)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(o.rect()), r, r)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return o


def thumb(pm, n, r=None):
    if pm.isNull():
        return pm
    t = pm.scaled(n, n, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return rounded(t.copy((t.width() - n) // 2, (t.height() - n) // 2, n, n), r if r is not None else n // 4.5)


# ==================== КАСТОМНЫЕ ВИДЖЕТЫ С ВЕКТОРНЫМИ ИКОНКАМИ ====================
class VectorBtn(QPushButton):
    """Кнопка с векторной Duotone-иконкой и плавной подсветкой."""
    def __init__(s, icon_name: str, text: str = '', badge_col: QColor = None, fn=None, h=42):
        super().__init__()
        s.icon_name = icon_name
        s.label_text = text
        s.badge_col = badge_col
        s.setCursor(Qt.PointingHandCursor)
        s.setFixedHeight(h)
        if not text:
            s.setFixedWidth(h)
        if fn:
            s.clicked.connect(fn)

    def setText(s, t: str):
        s.label_text = t
        s.update()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        hv = s.underMouse()
        pr = s.isDown()
        bg = QColor(255, 255, 255, 42 if pr else (26 if hv else 14)) if not STYLE['light'] else QColor(0, 0, 0, 26 if hv else 12)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(1, 1, s.width() - 2, s.height() - 2), 13, 13)

        fg = QColor('#141416') if STYLE['light'] else QColor('white')
        if not s.label_text:
            VectorIcon.draw(p, s.icon_name, QRectF(6, 6, s.width() - 12, s.height() - 12), fg, s.badge_col)
        else:
            ir = QRectF(8, (s.height() - 28) / 2, 28, 28)
            VectorIcon.draw(p, s.icon_name, ir, QColor('white') if s.badge_col else fg, s.badge_col)
            p.setPen(fg)
            p.setFont(fnt(9.8, QFont.DemiBold))
            p.drawText(QRectF(42, 0, s.width() - 46, s.height()), Qt.AlignVCenter | Qt.AlignLeft, s.label_text)


class TopBar(QWidget):
    """Верхняя навигационная панель с векторными иконками и пружинной капсулой."""
    changed = Signal(int)
    actionTriggered = Signal(str)

    def __init__(s, items):
        super().__init__()
        s.items = items  # [(icon_name, title), ...]
        s.idx = 0
        s.sx = Sp(4)
        s.sw = Sp(108)
        s.pinned = False
        s.badges = {}                       # индекс вкладки -> (число, цвет)
        s.setFixedHeight(38)
        s.setCursor(Qt.PointingHandCursor)

    def set_badge(s, idx, count, color):
        if count:
            s.badges[idx] = (int(count), color)
        else:
            s.badges.pop(idx, None)
        s.update()

    def _rects(s):
        res = []
        x = 4.0
        tf = fnt(9.5, QFont.DemiBold)
        fm = QFontMetrics(tf)
        for k, (_, name) in enumerate(s.items):
            w = fm.horizontalAdvance(name) + 44 if k == s.idx else 34
            res.append(QRectF(x, 3, w, 32))
            x += w + 4
        return res

    def _right_rects(s):
        w = s.width()
        return [
            ('voice', 'voice', QRectF(w - 114, 4, 30, 30)),
            ('pin', 'pin', QRectF(w - 78, 4, 30, 30)),
            ('settings', 'sys', QRectF(w - 42, 4, 30, 30)),
        ]

    def mousePressEvent(s, e):
        pt = e.position()
        for k, r in enumerate(s._rects()):
            if r.contains(pt):
                s.idx = k
                s.changed.emit(k)
                s.update()
                return
        for act, _, r in s._right_rects():
            if r.contains(pt):
                if act == 'pin':
                    s.pinned = not s.pinned
                s.actionTriggered.emit(act)
                s.update()
                return

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        rects = s._rects()
        if rects:
            tgt_r = rects[s.idx]
            s.sx.tgt, s.sw.tgt = tgt_r.x(), tgt_r.width()
            x, w = s.sx.step(.26, .66), s.sw.step(.26, .66)
            p.setPen(QPen(QColor(255, 255, 255, 28), 1))
            p.setBrush(QColor(255, 255, 255, 32) if not STYLE['light'] else QColor(0, 0, 0, 22))
            p.drawRoundedRect(QRectF(x, 3, w, 32), 16, 16)

        tf = fnt(9.5, QFont.DemiBold)
        fg = QColor('#141416') if STYLE['light'] else QColor('white')
        sub = QColor(20, 20, 22, 130) if STYLE['light'] else QColor(255, 255, 255, 135)

        for k, ((ic_name, name), r) in enumerate(zip(s.items, rects)):
            if k == s.idx:
                VectorIcon.draw(p, ic_name, QRectF(r.x() + 7, r.y() + 5, 22, 22), fg)
                p.setPen(fg)
                p.setFont(tf)
                p.drawText(QRectF(r.x() + 31, r.y(), r.width() - 36, r.height()), Qt.AlignVCenter | Qt.AlignLeft, name)
            else:
                VectorIcon.draw(p, ic_name, QRectF(r.x() + 6, r.y() + 5, 22, 22), sub)
            if k in s.badges:                                  # точка / счётчик непрочитанных
                n, bc = s.badges[k]
                cx_, cy_ = (r.x() + 27, r.y() + 7) if k != s.idx else (r.x() + 29, r.y() + 8)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(bc))
                p.drawEllipse(QPointF(cx_, cy_), 6.0 if n > 1 else 4.0, 6.0 if n > 1 else 4.0)
                if n > 1:
                    p.setPen(QColor('white'))
                    p.setFont(fnt(7.2, QFont.Bold))
                    p.drawText(QRectF(cx_ - 6, cy_ - 6, 12, 12), Qt.AlignCenter, str(min(n, 99)))

        for act, ic_name, r in s._right_rects():
            active = (act == 'pin' and s.pinned)
            p.setPen(Qt.NoPen)
            p.setBrush(STYLE['acc'] if active else QColor(255, 255, 255, 22 if not STYLE['light'] else 35))
            p.drawEllipse(r)
            VectorIcon.draw(p, ic_name, QRectF(r.x() + 5, r.y() + 5, 20, 20), QColor('white') if active else fg)


class Slider(QWidget):
    valueChanged = Signal(int)

    def __init__(s):
        super().__init__()
        s.v, s.h, s.drag = 50, Sp(5.5), False
        s.setFixedHeight(24)
        s.setCursor(Qt.PointingHandCursor)

    def setValue(s, v):
        s.v = int(clamp(v, 0, 100))
        s.update()

    def _set(s, x):
        v = int(clamp((x - 8) / max(s.width() - 16, 1)) * 100)
        if v != s.v:
            s.v = v
            s.valueChanged.emit(v)
            s.update()

    def mousePressEvent(s, e):
        s.drag = True
        s._set(e.position().x())

    def mouseMoveEvent(s, e):
        if s.drag:
            s._set(e.position().x())

    def mouseReleaseEvent(s, e):
        s.drag = False

    def wheelEvent(s, e):
        s.v = int(clamp(s.v + (3 if e.angleDelta().y() > 0 else -3), 0, 100))
        s.valueChanged.emit(s.v)
        s.update()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        cy = s.height() / 2
        s.h.tgt = 7.5 if (s.underMouse() or s.drag) else 5.0
        r = s.h.step(.3, .6)
        x0, x1 = 8., s.width() - 8.
        x = x0 + (x1 - x0) * s.v / 100
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40) if not STYLE['light'] else QColor(0, 0, 0, 35))
        p.drawRoundedRect(QRectF(x0, cy - 2.5, x1 - x0, 5), 2.5, 2.5)
        p.setBrush(STYLE['acc'])
        p.drawRoundedRect(QRectF(x0, cy - 2.5, max(x - x0, 0), 5), 2.5, 2.5)
        p.setBrush(QColor('white'))
        p.drawEllipse(QPointF(x, cy), r, r)
        if not s.h.settled(.05):
            s.update()

    def enterEvent(s, e):
        s.update()

    def leaveEvent(s, e):
        s.update()


class Bar(QWidget):
    """Полоса прогресса трека: клик или перетаскивание = перемотка в плеере."""
    seeked = Signal(float)          # доля 0..1 при отпускании мыши

    def __init__(s):
        super().__init__()
        s.m, s.v, s.drag = 1, 0, False
        s.hh = Sp(2.0)
        s.setFixedHeight(12)
        s.setCursor(Qt.PointingHandCursor)

    def setMaximum(s, m):
        s.m = max(m, 1)

    def setValue(s, v):
        if s.drag or v == s.v:
            return
        s.v = v
        s.update()

    def _frac(s, x):
        return clamp((x - 2) / max(s.width() - 4, 1))

    def enterEvent(s, e):
        s.update()

    def leaveEvent(s, e):
        s.update()

    def mousePressEvent(s, e):
        s.drag = True
        s.v = int(s._frac(e.position().x()) * s.m)
        s.update()

    def mouseMoveEvent(s, e):
        if s.drag:
            s.v = int(s._frac(e.position().x()) * s.m)
            s.update()

    def mouseReleaseEvent(s, e):
        if s.drag:
            s.drag = False
            s.seeked.emit(s._frac(e.position().x()))

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        cy, w = s.height() / 2, s.width() - 4.
        s.hh.tgt = 3.0 if (s.underMouse() or s.drag) else 2.0
        hh = s.hh.step(.3, .6)
        x = 2 + w * clamp(s.v / s.m)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 38) if STYLE['light'] else QColor(255, 255, 255, 40))
        p.drawRoundedRect(QRectF(2, cy - hh, w, hh * 2), hh, hh)
        p.setBrush(STYLE['acc'])
        p.drawRoundedRect(QRectF(2, cy - hh, max(x - 2, 0), hh * 2), hh, hh)
        if hh > 2.2:
            p.setBrush(QColor('white'))
            p.drawEllipse(QPointF(x, cy), hh + 1.6, hh + 1.6)
        if not s.hh.settled(.05):
            s.update()


class TimerRing(QWidget):
    def __init__(s):
        super().__init__()
        s.total = 25 * 60
        s.left = 25 * 60
        s.setFixedSize(92, 92)

    def set_time(s, left, total=None):
        s.left = max(0, left)
        if total:
            s.total = max(1, total)
        s.update()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(8, 8, s.width() - 16, s.height() - 16)
        p.setPen(QPen(QColor(255, 255, 255, 30), 6))
        p.drawEllipse(r)
        prog = clamp(s.left / max(s.total, 1))
        pen = QPen(QColor('#ff9f0a'), 6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 90 * 16, int(-prog * 360 * 16))
        p.setPen(QColor('#141416') if STYLE['light'] else QColor('white'))
        p.setFont(fnt(13, QFont.Bold))
        p.drawText(r, Qt.AlignCenter, f"{s.left // 60:02d}:{s.left % 60:02d}")


class AppBtn(QToolButton):
    droppedOn = Signal(int, int)

    def __init__(s, idx, kind='app'):
        super().__init__()
        s.idx = idx
        s.kind = kind
        s.setAcceptDrops(True)
        s.setCursor(Qt.PointingHandCursor)
        s.setFixedSize(40, 40)
        s.drag_start = None

    def mousePressEvent(s, e):
        if e.button() == Qt.LeftButton:
            s.drag_start = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(s, e):
        if (e.buttons() & Qt.LeftButton) and s.drag_start:
            if (e.position().toPoint() - s.drag_start).manhattanLength() > 14:
                d = QDrag(s)
                m = QMimeData()
                m.setText(f"island_app:{s.idx}")
                d.setMimeData(m)
                d.exec(Qt.MoveAction)
                return
        super().mouseMoveEvent(e)

    def dragEnterEvent(s, e):
        if e.mimeData().text().startswith("island_app:"):
            e.acceptProposedAction()

    def dropEvent(s, e):
        txt = e.mimeData().text()
        if txt.startswith("island_app:"):
            src = int(txt.split(":")[1])
            if src != s.idx:
                s.droppedOn.emit(src, s.idx)
            e.acceptProposedAction()

    def paintEvent(s, e):
        super().paintEvent(e)
        if s.kind in ('group', 'url'):
            p = QPainter(s)
            VectorIcon.draw(
                p, 'shelf' if s.kind == 'group' else 'cmd',
                QRectF(6, 6, 28, 28), QColor('white'),
                QColor('#5e5ce6') if s.kind == 'group' else QColor('#0a84ff')
            )


# ==================== ПЕРЕКЛЮЧАТЕЛИ И КАРТОЧКИ ТЕМ ====================
class Toggle(QCheckBox):
    """Анимированный переключатель."""
    def __init__(s, checked=False):
        super().__init__()
        s.setChecked(checked)
        s.setCursor(Qt.PointingHandCursor)
        s.setFixedSize(44, 24)
        s._t = 1.0 if checked else 0.0
        s._an = QVariantAnimation(s)
        s._an.setDuration(200)
        s._an.setEasingCurve(QEasingCurve.OutBack)
        s._an.valueChanged.connect(lambda v: (setattr(s, '_t', float(v)), s.update()))
        s.toggled.connect(s._go)

    def _go(s, on):
        s._an.stop()
        s._an.setStartValue(s._t)
        s._an.setEndValue(1.0 if on else 0.0)
        s._an.start()

    def hitButton(s, pos):
        return s.rect().contains(pos)

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        t = clamp(s._t)
        track = mix(QColor('#c7c7cc' if STYLE['light'] else '#3a3a3f'), STYLE['acc'], t)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 2, 44, 20), 10, 10)
        x = 12 + 20 * s._t
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QPointF(x, 13), 8.5, 8.5)
        p.setBrush(QColor('white'))
        p.drawEllipse(QPointF(x, 12), 8.5 + (1.2 if s.isDown() else 0), 8.5)


class Segmented(QWidget):
    """Сегментированный переключатель с пружинной «капсулой»."""
    changed = Signal(str)

    def __init__(s, options, current):
        super().__init__()
        s.opts, s.cur = options, current
        s.sx, s.sw, s._first = Sp(0), Sp(0), True
        s.setFixedHeight(34)
        s.setMinimumWidth(60 * len(options))
        s.setCursor(Qt.PointingHandCursor)

    def _rects(s):
        n, w = len(s.opts), s.width() / max(len(s.opts), 1)
        return [QRectF(i * w + 3, 3, w - 6, s.height() - 6) for i in range(n)]

    def setCurrent(s, key):
        s.cur = key
        s.update()

    def mousePressEvent(s, e):
        for (k, _), r in zip(s.opts, s._rects()):
            if r.contains(e.position()) and k != s.cur:
                s.cur = k
                s.changed.emit(k)
                s.update()
                return

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        lt = STYLE['light']
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 22) if lt else QColor(255, 255, 255, 16))
        p.drawRoundedRect(QRectF(0, 0, s.width(), s.height()), 12, 12)
        rects = s._rects()
        keys = [k for k, _ in s.opts]
        if s.cur in keys:
            tr = rects[keys.index(s.cur)]
            s.sx.tgt, s.sw.tgt = tr.x(), tr.width()
            if s._first:
                s.sx.snap(), s.sw.snap()
                s._first = False
            x, w = s.sx.step(.3, .62), s.sw.step(.3, .62)
            p.setBrush(STYLE['acc'])
            p.drawRoundedRect(QRectF(x, 3, w, s.height() - 6), 10, 10)
        p.setFont(fnt(9.6, QFont.DemiBold))
        for (k, name), r in zip(s.opts, rects):
            p.setPen(on_acc(STYLE['acc']) if k == s.cur else (QColor('#141416') if lt else QColor(255, 255, 255, 190)))
            p.drawText(r, Qt.AlignCenter, name)
        if not (s.sx.settled(.05) and s.sw.settled(.05)):
            s.update()


class ThemeCard(QWidget):
    """Карточка-превью темы."""
    picked = Signal(str)

    def __init__(s, key):
        super().__init__()
        s.key, s.sel = key, False
        s.setFixedSize(116, 76)
        s.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(s, e):
        s.picked.emit(s.key)

    @staticmethod
    def _mini(p, rect, th, acc):
        gr = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gr.setColorAt(0, QColor(th['base']))
        gr.setColorAt(1, QColor(th['base2']))
        p.setPen(QPen(QColor(acc), 1.2))
        p.setBrush(gr)
        p.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(acc))
        p.drawEllipse(QPointF(rect.x() + 11, rect.center().y()), 3.6, 3.6)
        p.setBrush(QColor(20, 20, 22, 150) if th['light'] else QColor(255, 255, 255, 150))
        p.drawRoundedRect(QRectF(rect.x() + 21, rect.center().y() - 1.6, rect.width() - 34, 3.2), 1.6, 1.6)

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1.5, 1.5, s.width() - 3, s.height() - 3)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.save()
        p.setClipPath(path)
        if s.key == 'system':
            dk, lt = THEMES['obsidian'], THEMES['light']
            p.fillRect(QRectF(r.x(), r.y(), r.width() / 2, r.height()), QColor(dk['card_end']))
            p.fillRect(QRectF(r.center().x(), r.y(), r.width() / 2, r.height()), QColor(lt['card_end']))
            ThemeCard._mini(p, QRectF(r.x() + 12, r.y() + 10, r.width() - 24, 18), dk if not is_win_light() else lt, dk['acc'])
            name, light_name = 'Как в Windows', False
        else:
            th = THEMES[s.key]
            p.fillRect(r, QColor(th['card_end']))
            ThemeCard._mini(p, QRectF(r.x() + 12, r.y() + 10, r.width() - 24, 18), th, th['acc'])
            name, light_name = th['name'], th['light']
        p.restore()
        p.setPen(QColor('#141416') if (light_name and s.key != 'system') else QColor('white'))
        if s.key == 'system':
            p.setPen(QColor(255, 255, 255, 230))
        p.setFont(fnt(9.6, QFont.DemiBold))
        p.drawText(QRectF(r.x(), r.y() + 38, r.width(), 26), Qt.AlignCenter, name)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(STYLE['acc'], 2.4) if s.sel else QPen(QColor(255, 255, 255, 28) if not STYLE['light'] else QColor(0, 0, 0, 40), 1))
        p.drawRoundedRect(r, 14, 14)


class PillButton(QPushButton):
    """Кнопка-«таблетка» с плавной подсветкой при наведении и лёгким сжатием при нажатии (пружины, как у остального острова)."""

    def __init__(s, text=''):
        super().__init__(text)
        s.hv, s.pr = Sp(0), Sp(0)
        s.setCursor(Qt.PointingHandCursor)
        s.setMinimumHeight(32)

    def sizeHint(s):
        return QSize(QFontMetrics(fnt(9.8, QFont.DemiBold)).horizontalAdvance(s.text()) + 30, 32)

    def minimumSizeHint(s):
        return s.sizeHint()

    def enterEvent(s, e):
        s.update()

    def leaveEvent(s, e):
        s.update()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        s.hv.tgt = 1.0 if (s.underMouse() and s.isEnabled()) else 0.0
        s.pr.tgt = 1.0 if s.isDown() else 0.0
        h, d = s.hv.step(.3, .62), s.pr.step(.4, .6)
        light = STYLE['light']
        fg = QColor('#141416') if light else QColor('white')
        if s.isChecked():
            bg = QColor(STYLE['acc'])
            bg.setAlpha(int(205 + 35 * h))
            fg = QColor('white')
        else:
            a = 18 + 26 * h
            bg = QColor(0, 0, 0, int(a * 0.7)) if light else QColor(255, 255, 255, int(a))
        w_, h_ = s.width(), s.height()
        p.translate(w_ / 2, h_ / 2)
        k = 1.0 - 0.04 * d
        p.scale(k, k)
        p.translate(-w_ / 2, -h_ / 2)
        p.setOpacity(1.0 if s.isEnabled() else 0.4)
        p.setPen(QPen(QColor(0, 0, 0, int(10 + 14 * h)) if light else QColor(255, 255, 255, int(12 + 18 * h)), 1))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0.5, 0.5, w_ - 1, h_ - 1), min(15, h_ / 2), min(15, h_ / 2))
        p.setPen(fg)
        p.setFont(fnt(9.8, QFont.DemiBold))
        p.drawText(QRectF(0, 0, w_, h_), Qt.AlignCenter, s.text())
        if not (s.hv.settled(.01) and s.pr.settled(.01)):
            s.update()


class IconBtn(QPushButton):
    """Круглая кнопка с векторной иконкой: плавная подсветка, сжатие при нажатии, акцентный и «активный» (пульс) режимы."""

    def __init__(s, icon_name: str, tip: str = '', size: int = 30, accent: bool = False, fn=None):
        super().__init__()
        s.icon_name, s.accent, s.active_col = icon_name, accent, None
        s.hv, s.pr = Sp(0), Sp(0)
        s.setCursor(Qt.PointingHandCursor)
        s.setFixedSize(size, size)
        if tip:
            s.setToolTip(tip)
        if fn:
            s.clicked.connect(fn)

    def set_icon(s, name: str):
        s.icon_name = name
        s.update()

    def set_active(s, col=None):
        """col — цвет «горящей» кнопки (идёт запись голоса); None — обычная."""
        s.active_col = QColor(col) if col else None
        s.update()

    def paintEvent(s, e):
        import math
        import time
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        s.hv.tgt = 1.0 if (s.underMouse() and s.isEnabled()) else 0.0
        s.pr.tgt = 1.0 if s.isDown() else 0.0
        h, d = s.hv.step(.3, .62), s.pr.step(.4, .6)
        light = STYLE['light']
        w_, h_ = s.width(), s.height()
        p.translate(w_ / 2, h_ / 2)
        k = 1.0 - 0.08 * d
        p.scale(k, k)
        p.translate(-w_ / 2, -h_ / 2)
        p.setOpacity(1.0 if s.isEnabled() else 0.4)
        r = QRectF(1, 1, w_ - 2, h_ - 2)
        if s.active_col is not None:
            pulse = 0.5 + 0.5 * math.sin(time.time() * 6.0)
            ring = QColor(s.active_col)
            ring.setAlpha(int(40 + 70 * pulse))
            p.setPen(Qt.NoPen)
            p.setBrush(ring)
            grow = 2.5 * pulse
            p.drawEllipse(r.adjusted(-grow, -grow, grow, grow))
            p.setBrush(s.active_col)
            p.drawEllipse(r)
            VectorIcon.draw(p, s.icon_name, r.adjusted(w_ * .2, h_ * .2, -w_ * .2, -h_ * .2), QColor('white'))
            s.update()
            return
        if s.accent:
            acc = QColor(STYLE['acc'])
            acc.setAlpha(int(215 + 40 * h))
            p.setPen(Qt.NoPen)
            p.setBrush(acc)
            p.drawEllipse(r)
            VectorIcon.draw(p, s.icon_name, r.adjusted(w_ * .2, h_ * .2, -w_ * .2, -h_ * .2), on_acc(STYLE['acc']))
        else:
            a = 0 if not h else int((14 if not light else 12) + 22 * h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, a) if light else QColor(255, 255, 255, a))
            p.drawEllipse(r)
            fg = QColor('#141416') if light else QColor('white')
            fg.setAlpha(int(165 + 90 * h))
            VectorIcon.draw(p, s.icon_name, r.adjusted(w_ * .2, h_ * .2, -w_ * .2, -h_ * .2), fg)
        if not (s.hv.settled(.01) and s.pr.settled(.01)):
            s.update()
