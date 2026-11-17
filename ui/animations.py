"""Пружинная физика острова и миксин отрисовки «жидкой» формы и персонажей."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainterPath
from core.utils import clamp


# (жёсткость, сохранение скорости, название) — параметры пружин острова
ANIM_STYLES = {'liquid': (.20, .68, 'Жидкая'), 'smooth': (.16, .50, 'Плавная'), 'snappy': (.30, .52, 'Резкая')}


class Sp:
    """Пружина с фиксированным шагом интегрирования: одинаковое поведение на 60/120/144/240 Гц.
    k — жёсткость, d — сохранение скорости за кадр 16 мс (параметры совместимы со старой версией)."""
    __slots__ = ('x', 'v', 'tgt')

    def __init__(s, x):
        s.x, s.v, s.tgt = float(x), 0.0, float(x)

    def step(s, k=.20, d=.68, dt=0.016):
        n = max(1, min(16, int(math.ceil(dt / 0.004))))
        r = (dt / n) / 0.016
        kk, dd = k * r, d ** r
        for _ in range(n):
            s.v = (s.v + (s.tgt - s.x) * kk) * dd
            s.x += s.v * r
        return s.x

    def snap(s, x=None):
        s.x = s.tgt = float(s.tgt if x is None else x)
        s.v = 0.0

    def settled(s, eps=0.35) -> bool:
        return abs(s.tgt - s.x) < eps and abs(s.v) < eps


class AnimationMixin:
    """Часть класса Island: AnimationMixin."""

    def liquid_path(s, cx, w, h, g=0.0, now=0.0):
        main = g == 0
        # «Желе»: при раскрытии низ острова выпячивается, при отскоке — втягивается; ширина слегка пружинит
        jelly = clamp(s.sh.v * 0.5, -6.0, 8.0) if main else 0.0
        sq = clamp(-s.sh.v * 0.10, -3.5, 3.5) if main else 0.0
        # растягивание капсулы: пока ширина быстро растёт, форма тянется в стороны и чуть приплющивается (объём сохраняется)
        sx = clamp(s.sw.v / max(w, 60.0) * 0.5, -0.05, 0.06) if main else 0.0
        w *= 1.0 + sx
        h = h * (1.0 - 0.8 * sx) if main else h
        x0, x1 = cx - w / 2 - g - sq, cx + w / 2 + g + sq
        ear = 14.0 if h > 20 else 6.0
        r = min(22.0 + g, h / 2)
        bh = h + g

        path = QPainterPath()
        path.moveTo(x0 - ear, 0)
        path.quadTo(x0, 0, x0, min(ear, bh - r))
        path.lineTo(x0, bh - r)
        path.quadTo(x0, bh, x0 + r, bh)

        steps = 44 if main else 2             # у ореола форма простая — лишние точки не нужны
        span = (x1 - r) - (x0 + r)
        use_eq = main and s.cfg.get('edge_eq', True) and s.playing and not s.dodging
        for i in range(1, steps + 1):
            t = i / steps
            px = (x0 + r) + span * t
            py = bh
            if main:
                if s.bh.x > 0.3:
                    dist = (px - (cx + s.bx.x)) / 42.0
                    py += s.bh.x * math.exp(-dist * dist)
                if use_eq:
                    amp = 3.6 if s.mode == 'idle' else 2.4
                    py += amp * math.sin(t * math.pi) * abs(math.sin(t * 24 - now * 8.0) * math.cos(t * 11 + now * 5.0))
                if jelly:
                    py += jelly * math.sin(t * math.pi)
            path.lineTo(px, py)

        path.quadTo(x1, bh, x1, bh - r)
        path.lineTo(x1, min(ear, bh - r))
        path.quadTo(x1, 0, x1 + ear, 0)
        path.closeSubpath()
        return path

    def draw_character(s, p, x, y, ch_type, now):
        mp = QCursor.pos()
        dx = clamp((mp.x() - (s.x() + x)) / 250.0, -1.0, 1.0) * 2.4
        dy = clamp((mp.y() - (s.y() + y)) / 250.0, -1.0, 1.0) * 1.8
        p.save()
        p.translate(x, y)
        if ch_type == 'astro':
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('white'))
            p.drawRoundedRect(QRectF(-10, -9, 20, 18), 8, 8)
            p.setBrush(QColor('#5ac8fa'))
            p.drawRoundedRect(QRectF(-7, -4, 14, 8), 4, 4)
            p.setBrush(QColor('#111'))
            p.drawEllipse(QPointF(-3 + dx, dy), 1.6, 2.0)
            p.drawEllipse(QPointF(3 + dx, dy), 1.6, 2.0)
        elif ch_type == 'cat':
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('white'))
            p.drawRoundedRect(QRectF(-10, -7, 20, 16), 7, 7)
            p.setBrush(QColor('#111'))
            p.drawEllipse(QPointF(-3.5 + dx, dy), 1.7, 2.1)
            p.drawEllipse(QPointF(3.5 + dx, dy), 1.7, 2.1)
            p.setBrush(QColor('#ff4d6d'))
            p.drawEllipse(QPointF(0, 3), 1.5, 1.2)
        elif ch_type == 'pixel':
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#ff8a65'))
            p.drawRect(QRectF(-9, -7, 18, 14))
            p.setBrush(QColor('#111'))
            p.drawRect(QRectF(-5 + dx, -2 + dy, 3, 3))
            p.drawRect(QRectF(2 + dx, -2 + dy, 3, 3))
        elif ch_type == 'eyes':
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('white'))
            p.drawEllipse(QPointF(-5, 0), 4.5, 5.5)
            p.drawEllipse(QPointF(5, 0), 4.5, 5.5)
            p.setBrush(QColor('#111'))
            p.drawEllipse(QPointF(-5 + dx, dy), 2.2, 2.5)
            p.drawEllipse(QPointF(5 + dx, dy), 2.2, 2.5)
        elif ch_type == 'fire':
            p.setPen(Qt.NoPen)
            for k, col in ((8, '#ff453a'), (5.5, '#ff9f0a'), (3, '#ffd60a')):
                fh = k + 2 * math.sin(now * 9 + k)
                p.setBrush(QColor(col))
                p.drawEllipse(QPointF(0, 3 - fh / 3), k * 0.8, fh)
        p.restore()
