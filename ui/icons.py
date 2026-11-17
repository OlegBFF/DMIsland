"""Векторные иконки, рисуемые QPainter."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


# ==================== ВЕКТОРНЫЙ РЕНДЕРЕР ИКОНОК (DUOTONE & VECTOR) ====================
class VectorIcon:
    """Векторные duotone-иконки: контур + полупрозрачная заливка, толщина линии масштабируется с размером."""
    @staticmethod
    def draw(p: QPainter, name: str, rect: QRectF, color: QColor = QColor('white'), badge_col: QColor = None):
        fn = getattr(VectorIcon, '_i_' + name, None)
        if fn is None:
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = rect.center().x(), rect.center().y()
        r = min(rect.width(), rect.height()) * 0.42

        if badge_col:
            rr = rect.height() * 0.34
            bg = QLinearGradient(rect.topLeft(), rect.bottomRight())
            bg.setColorAt(0, badge_col.lighter(118))
            bg.setColorAt(1, badge_col.darker(128))
            p.setPen(QPen(QColor(255, 255, 255, 45), 1))
            p.setBrush(bg)
            p.drawRoundedRect(rect, rr, rr)
            # мягкий верхний блик
            gl = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.center().y()))
            gl.setColorAt(0, QColor(255, 255, 255, 58))
            gl.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(gl)
            p.drawRoundedRect(QRectF(rect.x() + 1, rect.y() + 1, rect.width() - 2, rect.height() / 2), rr, rr)

        fill = QColor(color)
        fill.setAlpha(64 if badge_col else 48)
        p.setPen(QPen(color, max(1.6, r * 0.2), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        fn(p, cx, cy, r, color, fill)
        p.restore()

    # ---------- навигация и инструменты ----------
    @staticmethod
    def _i_home(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.7, cy - r * 0.15, r * 1.4, r * 1.05), 2.5, 2.5)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - r, cy - r * 0.1)
        path.lineTo(cx, cy - r * 0.95)
        path.lineTo(cx + r, cy - r * 0.1)
        p.drawPath(path)
        p.drawLine(QPointF(cx, cy + r * 0.9), QPointF(cx, cy + r * 0.4))

    @staticmethod
    def _i_clip(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.75, cy - r * 0.7, r * 1.5, r * 1.65), 3, 3)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(cx - r * 0.35, cy - r * 0.95, r * 0.7, r * 0.4), 1.5, 1.5)

    @staticmethod
    def _i_shelf(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.85, cy - r * 0.75, r * 1.7, r * 1.5), 3.5, 3.5)
        p.drawLine(QPointF(cx - r * 0.85, cy + r * 0.1), QPointF(cx + r * 0.85, cy + r * 0.1))
        p.drawLine(QPointF(cx, cy - r * 0.45), QPointF(cx, cy + r * 0.45))

    @staticmethod
    def _i_text(p, cx, cy, r, c, f):
        p.drawLine(QPointF(cx - r * 0.75, cy - r * 0.75), QPointF(cx + r * 0.75, cy - r * 0.75))
        p.drawLine(QPointF(cx, cy - r * 0.75), QPointF(cx, cy + r * 0.85))
        p.drawLine(QPointF(cx - r * 0.35, cy + r * 0.85), QPointF(cx + r * 0.35, cy + r * 0.85))

    @staticmethod
    def _i_chat(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.85, cy - r * 0.75, r * 1.7, r * 1.3), 5, 5)
        p.drawLine(QPointF(cx - r * 0.3, cy + r * 0.55), QPointF(cx - r * 0.6, cy + r * 0.9))

    @staticmethod
    def _i_notes(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.75, cy - r * 0.85, r * 1.5, r * 1.7), 3, 3)
        for dy in (-0.3, 0.1, 0.5):
            p.drawLine(QPointF(cx - r * 0.4, cy + r * dy), QPointF(cx + r * 0.4, cy + r * dy))

    @staticmethod
    def _i_sun(p, cx, cy, r, c, f):
        p.setPen(QPen(QColor('#ffd60a'), max(1.6, r * 0.2), Qt.SolidLine, Qt.RoundCap))
        p.setBrush(QColor('#ffcc00'))
        p.drawEllipse(QPointF(cx, cy), r * 0.48, r * 0.48)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(cx + math.cos(a) * r * 0.68, cy + math.sin(a) * r * 0.68),
                       QPointF(cx + math.cos(a) * r * 0.95, cy + math.sin(a) * r * 0.95))

    _i_weather = _i_sun

    @staticmethod
    def _i_sys(p, cx, cy, r, c, f):
        for dy, ox in ((-0.5, -0.25), (0.0, 0.3), (0.5, -0.1)):
            p.drawLine(QPointF(cx - r * 0.8, cy + r * dy), QPointF(cx + r * 0.8, cy + r * dy))
            p.setBrush(c)
            p.drawEllipse(QPointF(cx + r * ox, cy + r * dy), 2.3, 2.3)

    @staticmethod
    def _i_area(p, cx, cy, r, c, f):
        s = r * 0.85
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            p.drawLine(QPointF(cx + sx * s, cy + sy * s), QPointF(cx + sx * s * 0.45, cy + sy * s))
            p.drawLine(QPointF(cx + sx * s, cy + sy * s), QPointF(cx + sx * s, cy + sy * s * 0.45))

    @staticmethod
    def _i_full(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.9, cy - r * 0.65, r * 1.8, r * 1.2), 2.5, 2.5)
        p.drawLine(QPointF(cx - r * 0.4, cy + r * 0.85), QPointF(cx + r * 0.4, cy + r * 0.85))

    _i_monitor = _i_full

    @staticmethod
    def _i_ocr(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.85, cy - r * 0.85, r * 1.7, r * 1.7), 3.5, 3.5)
        p.drawLine(QPointF(cx - r * 0.45, cy - r * 0.25), QPointF(cx + r * 0.45, cy - r * 0.25))
        p.drawLine(QPointF(cx - r * 0.45, cy + r * 0.25), QPointF(cx + r * 0.2, cy + r * 0.25))

    @staticmethod
    def _i_qr(p, cx, cy, r, c, f):
        p.setBrush(f)
        for ox, oy in ((-0.75, -0.75), (0.15, -0.75), (-0.75, 0.15)):
            p.drawRoundedRect(QRectF(cx + r * ox, cy + r * oy, r * 0.6, r * 0.6), 1.5, 1.5)
        p.drawPoint(QPointF(cx + r * 0.45, cy + r * 0.45))

    @staticmethod
    def _i_pick(p, cx, cy, r, c, f):
        p.drawLine(QPointF(cx - r * 0.65, cy + r * 0.65), QPointF(cx + r * 0.25, cy - r * 0.25))
        p.setBrush(c)
        p.drawEllipse(QPointF(cx + r * 0.45, cy - r * 0.45), r * 0.32, r * 0.32)

    @staticmethod
    def _i_plain(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.7, cy - r * 0.5, r * 1.4, r * 1.0), 3, 3)
        p.drawLine(QPointF(cx - r * 0.7, cy - r * 0.5), QPointF(cx + r * 0.7, cy + r * 0.5))

    @staticmethod
    def _i_rec(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.9, cy - r * 0.55, r * 1.25, r * 1.1), 3, 3)
        poly = QPainterPath()
        poly.moveTo(cx + r * 0.35, cy)
        poly.lineTo(cx + r * 0.9, cy - r * 0.45)
        poly.lineTo(cx + r * 0.9, cy + r * 0.45)
        poly.closeSubpath()
        p.drawPath(poly)

    @staticmethod
    def _i_cmd(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawEllipse(QPointF(cx - r * 0.15, cy - r * 0.15), r * 0.6, r * 0.6)
        p.drawLine(QPointF(cx + r * 0.3, cy + r * 0.3), QPointF(cx + r * 0.8, cy + r * 0.8))

    @staticmethod
    def _i_voice(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.32, cy - r * 0.8, r * 0.64, r * 1.05), 3.5, 3.5)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - r * 0.65, cy - r * 0.4, r * 1.3, r * 0.95), 180 * 16, 180 * 16)
        p.drawLine(QPointF(cx, cy + r * 0.55), QPointF(cx, cy + r * 0.88))

    _i_mic = _i_voice

    @staticmethod
    def _i_pin(p, cx, cy, r, c, f):
        p.setBrush(c)
        p.drawEllipse(QPointF(cx, cy - r * 0.3), r * 0.42, r * 0.42)
        p.drawLine(QPointF(cx, cy + r * 0.1), QPointF(cx, cy + r * 0.85))

    # ---------- плеер ----------
    @staticmethod
    def _i_play(p, cx, cy, r, c, f):
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        path = QPainterPath()
        path.moveTo(cx - r * 0.4, cy - r * 0.65)
        path.lineTo(cx + r * 0.65, cy)
        path.lineTo(cx - r * 0.4, cy + r * 0.65)
        path.closeSubpath()
        p.drawPath(path)

    @staticmethod
    def _i_pause(p, cx, cy, r, c, f):
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(cx - r * 0.55, cy - r * 0.6, r * 0.36, r * 1.2), 1.5, 1.5)
        p.drawRoundedRect(QRectF(cx + r * 0.19, cy - r * 0.6, r * 0.36, r * 1.2), 1.5, 1.5)

    @staticmethod
    def _i_prev(p, cx, cy, r, c, f):
        p.setBrush(c)
        p.drawLine(QPointF(cx - r * 0.55, cy - r * 0.55), QPointF(cx - r * 0.55, cy + r * 0.55))
        path = QPainterPath()
        path.moveTo(cx + r * 0.55, cy - r * 0.55)
        path.lineTo(cx - r * 0.35, cy)
        path.lineTo(cx + r * 0.55, cy + r * 0.55)
        path.closeSubpath()
        p.drawPath(path)

    @staticmethod
    def _i_next(p, cx, cy, r, c, f):
        p.setBrush(c)
        p.drawLine(QPointF(cx + r * 0.55, cy - r * 0.55), QPointF(cx + r * 0.55, cy + r * 0.55))
        path = QPainterPath()
        path.moveTo(cx - r * 0.55, cy - r * 0.55)
        path.lineTo(cx + r * 0.35, cy)
        path.lineTo(cx - r * 0.55, cy + r * 0.55)
        path.closeSubpath()
        p.drawPath(path)

    @staticmethod
    def _i_music(p, cx, cy, r, c, f):
        p.setBrush(c)
        p.drawEllipse(QPointF(cx - r * 0.4, cy + r * 0.55), r * 0.3, r * 0.25)
        p.drawEllipse(QPointF(cx + r * 0.55, cy + r * 0.35), r * 0.3, r * 0.25)
        p.drawLine(QPointF(cx - r * 0.1, cy + r * 0.55), QPointF(cx - r * 0.1, cy - r * 0.7))
        p.drawLine(QPointF(cx + r * 0.85, cy + r * 0.35), QPointF(cx + r * 0.85, cy - r * 0.9))
        p.drawLine(QPointF(cx - r * 0.1, cy - r * 0.7), QPointF(cx + r * 0.85, cy - r * 0.9))

    # ---------- система и устройства ----------
    @staticmethod
    def _i_wifi(p, cx, cy, r, c, f):
        for k in (0.95, 0.6, 0.25):
            p.drawArc(QRectF(cx - r * k, cy - r * k + r * 0.3, r * k * 2, r * k * 2), 45 * 16, 90 * 16)

    @staticmethod
    def _i_bt(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx - r * 0.4, cy - r * 0.45)
        path.lineTo(cx + r * 0.4, cy + r * 0.45)
        path.lineTo(cx, cy + r * 0.85)
        path.lineTo(cx, cy - r * 0.85)
        path.lineTo(cx + r * 0.4, cy - r * 0.45)
        path.lineTo(cx - r * 0.4, cy + r * 0.45)
        p.drawPath(path)

    @staticmethod
    def _i_bat(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.85, cy - r * 0.45, r * 1.5, r * 0.9), 2.5, 2.5)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(cx - r * 0.65, cy - r * 0.25, r * 0.9, r * 0.5), 1, 1)
        p.drawRect(QRectF(cx + r * 0.68, cy - r * 0.2, r * 0.18, r * 0.4))

    @staticmethod
    def _i_lock(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.65, cy - r * 0.1, r * 1.3, r * 0.95), 3, 3)
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - r * 0.4, cy - r * 0.75, r * 0.8, r * 0.9), 0, 180 * 16)

    @staticmethod
    def _i_power(p, cx, cy, r, c, f):
        p.drawArc(QRectF(cx - r * 0.7, cy - r * 0.65, r * 1.4, r * 1.4), -60 * 16, 300 * 16)
        p.drawLine(QPointF(cx, cy - r * 0.85), QPointF(cx, cy - r * 0.1))

    @staticmethod
    def _i_gear(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawEllipse(QPointF(cx, cy), r * 0.58, r * 0.58)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(QPointF(cx + math.cos(a) * r * 0.8, cy + math.sin(a) * r * 0.8),
                       QPointF(cx + math.cos(a) * r * 1.0, cy + math.sin(a) * r * 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r * 0.22, r * 0.22)

    @staticmethod
    def _i_usb(p, cx, cy, r, c, f):
        p.drawLine(QPointF(cx, cy + r * 0.6), QPointF(cx, cy - r * 0.8))
        p.setBrush(c)
        p.drawEllipse(QPointF(cx, cy + r * 0.78), r * 0.2, r * 0.2)
        tri = QPainterPath()
        tri.moveTo(cx, cy - r * 1.0)
        tri.lineTo(cx - r * 0.2, cy - r * 0.7)
        tri.lineTo(cx + r * 0.2, cy - r * 0.7)
        tri.closeSubpath()
        p.drawPath(tri)
        p.setBrush(Qt.NoBrush)
        left = QPainterPath()
        left.moveTo(cx, cy + r * 0.15)
        left.lineTo(cx - r * 0.55, cy - r * 0.1)
        left.lineTo(cx - r * 0.55, cy - r * 0.3)
        p.drawPath(left)
        right = QPainterPath()
        right.moveTo(cx, cy - r * 0.1)
        right.lineTo(cx + r * 0.55, cy - r * 0.35)
        right.lineTo(cx + r * 0.55, cy - r * 0.45)
        p.drawPath(right)
        p.setBrush(c)
        p.drawEllipse(QPointF(cx - r * 0.55, cy - r * 0.42), r * 0.15, r * 0.15)
        p.drawRect(QRectF(cx + r * 0.42, cy - r * 0.68, r * 0.26, r * 0.26))

    @staticmethod
    def _i_headphones(p, cx, cy, r, c, f):
        p.drawArc(QRectF(cx - r * 0.8, cy - r * 0.9, r * 1.6, r * 1.6), 0, 180 * 16)
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.92, cy - r * 0.05, r * 0.42, r * 0.8), 2.5, 2.5)
        p.drawRoundedRect(QRectF(cx + r * 0.5, cy - r * 0.05, r * 0.42, r * 0.8), 2.5, 2.5)

    @staticmethod
    def _i_bolt(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx + r * 0.2, cy - r * 0.95)
        path.lineTo(cx - r * 0.55, cy + r * 0.1)
        path.lineTo(cx - r * 0.05, cy + r * 0.1)
        path.lineTo(cx - r * 0.2, cy + r * 0.95)
        path.lineTo(cx + r * 0.55, cy - r * 0.15)
        path.lineTo(cx + r * 0.05, cy - r * 0.15)
        path.closeSubpath()
        p.setBrush(c)
        p.drawPath(path)

    @staticmethod
    def _i_cam(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.9, cy - r * 0.55, r * 1.8, r * 1.15), 3.5, 3.5)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(cx, cy + r * 0.03), r * 0.38, r * 0.38)

    @staticmethod
    def _i_game(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.95, cy - r * 0.5, r * 1.9, r * 1.05), r * 0.5, r * 0.5)
        p.drawLine(QPointF(cx - r * 0.6, cy + r * 0.02), QPointF(cx - r * 0.2, cy + r * 0.02))
        p.drawLine(QPointF(cx - r * 0.4, cy - r * 0.18), QPointF(cx - r * 0.4, cy + r * 0.22))
        p.setBrush(c)
        p.drawEllipse(QPointF(cx + r * 0.3, cy - r * 0.02), 1.4, 1.4)
        p.drawEllipse(QPointF(cx + r * 0.58, cy + r * 0.14), 1.4, 1.4)

    @staticmethod
    def _i_moon(p, cx, cy, r, c, f):
        a, b = QPainterPath(), QPainterPath()
        a.addEllipse(QPointF(cx, cy), r * 0.85, r * 0.85)
        b.addEllipse(QPointF(cx + r * 0.5, cy - r * 0.35), r * 0.72, r * 0.72)
        p.setBrush(f)
        p.drawPath(a.subtracted(b))

    @staticmethod
    def _i_palette(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawEllipse(QPointF(cx, cy), r * 0.95, r * 0.9)
        p.setBrush(c)
        for ox, oy in ((-0.4, -0.3), (0.1, -0.5), (0.5, -0.1), (-0.5, 0.25)):
            p.drawEllipse(QPointF(cx + r * ox, cy + r * oy), r * 0.11, r * 0.11)

    @staticmethod
    def _i_check(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx - r * 0.7, cy + r * 0.05)
        path.lineTo(cx - r * 0.2, cy + r * 0.55)
        path.lineTo(cx + r * 0.75, cy - r * 0.5)
        p.drawPath(path)

    @staticmethod
    def _i_close(p, cx, cy, r, c, f):
        p.drawLine(QPointF(cx - r * 0.6, cy - r * 0.6), QPointF(cx + r * 0.6, cy + r * 0.6))
        p.drawLine(QPointF(cx + r * 0.6, cy - r * 0.6), QPointF(cx - r * 0.6, cy + r * 0.6))

    @staticmethod
    def _i_bell(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx - r * 0.7, cy + r * 0.45)
        path.cubicTo(cx - r * 0.7, cy - r * 0.3, cx - r * 0.45, cy - r * 0.8, cx, cy - r * 0.8)
        path.cubicTo(cx + r * 0.45, cy - r * 0.8, cx + r * 0.7, cy - r * 0.3, cx + r * 0.7, cy + r * 0.45)
        path.closeSubpath()
        p.setBrush(f)
        p.drawPath(path)
        p.drawLine(QPointF(cx - r * 0.9, cy + r * 0.45), QPointF(cx + r * 0.9, cy + r * 0.45))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(cx - r * 0.22, cy + r * 0.52, r * 0.44, r * 0.36), 180 * 16, 180 * 16)

    @staticmethod
    def _i_folder(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.9, cy - r * 0.4, r * 1.8, r * 1.2), 3, 3)
        p.setBrush(Qt.NoBrush)
        tab = QPainterPath()
        tab.moveTo(cx - r * 0.9, cy - r * 0.35)
        tab.lineTo(cx - r * 0.9, cy - r * 0.7)
        tab.lineTo(cx - r * 0.25, cy - r * 0.7)
        tab.lineTo(cx, cy - r * 0.38)
        p.drawPath(tab)

    @staticmethod
    def _i_shield(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx, cy - r * 0.95)
        path.lineTo(cx + r * 0.8, cy - r * 0.55)
        path.cubicTo(cx + r * 0.8, cy + r * 0.3, cx + r * 0.4, cy + r * 0.7, cx, cy + r * 0.95)
        path.cubicTo(cx - r * 0.4, cy + r * 0.7, cx - r * 0.8, cy + r * 0.3, cx - r * 0.8, cy - r * 0.55)
        path.closeSubpath()
        p.setBrush(f)
        p.drawPath(path)

    @staticmethod
    def _i_spark(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.quadTo(cx, cy, cx + r, cy)
        path.quadTo(cx, cy, cx, cy + r)
        path.quadTo(cx, cy, cx - r, cy)
        path.quadTo(cx, cy, cx, cy - r)
        p.setBrush(c)
        p.drawPath(path)

    @staticmethod
    def _i_info(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawEllipse(QPointF(cx, cy), r * 0.9, r * 0.9)
        p.drawLine(QPointF(cx, cy - r * 0.05), QPointF(cx, cy + r * 0.45))
        p.drawPoint(QPointF(cx, cy - r * 0.42))

    # ---------- чат и уведомления ----------
    @staticmethod
    def _i_plus(p, cx, cy, r, c, f):
        p.drawLine(QPointF(cx - r * 0.7, cy), QPointF(cx + r * 0.7, cy))
        p.drawLine(QPointF(cx, cy - r * 0.7), QPointF(cx, cy + r * 0.7))

    @staticmethod
    def _i_send(p, cx, cy, r, c, f):
        p.drawLine(QPointF(cx, cy + r * 0.75), QPointF(cx, cy - r * 0.7))
        path = QPainterPath()
        path.moveTo(cx - r * 0.6, cy - r * 0.1)
        path.lineTo(cx, cy - r * 0.75)
        path.lineTo(cx + r * 0.6, cy - r * 0.1)
        p.drawPath(path)

    @staticmethod
    def _i_stop(p, cx, cy, r, c, f):
        p.setBrush(c)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(cx - r * 0.55, cy - r * 0.55, r * 1.1, r * 1.1), r * 0.22, r * 0.22)

    @staticmethod
    def _i_copy(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.2, cy - r * 0.2, r * 1.0, r * 1.05), 2.5, 2.5)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - r * 0.35, cy + r * 0.45)
        path.lineTo(cx - r * 0.75, cy + r * 0.45)
        path.lineTo(cx - r * 0.75, cy - r * 0.8)
        path.lineTo(cx + r * 0.2, cy - r * 0.8)
        path.lineTo(cx + r * 0.2, cy - r * 0.4)
        p.drawPath(path)

    @staticmethod
    def _i_link(p, cx, cy, r, c, f):
        p.save()
        p.translate(cx, cy)
        p.rotate(-45)
        p.drawRoundedRect(QRectF(-r * 0.95, -r * 0.32, r * 1.1, r * 0.64), r * 0.32, r * 0.32)
        p.drawRoundedRect(QRectF(-r * 0.15, -r * 0.32, r * 1.1, r * 0.64), r * 0.32, r * 0.32)
        p.restore()

    @staticmethod
    def _i_image(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawRoundedRect(QRectF(cx - r * 0.9, cy - r * 0.7, r * 1.8, r * 1.4), 3, 3)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - r * 0.9, cy + r * 0.45)
        path.lineTo(cx - r * 0.3, cy - r * 0.1)
        path.lineTo(cx + r * 0.15, cy + r * 0.3)
        path.lineTo(cx + r * 0.45, cy)
        path.lineTo(cx + r * 0.9, cy + r * 0.4)
        p.drawPath(path)
        p.drawPoint(QPointF(cx + r * 0.4, cy - r * 0.35))

    @staticmethod
    def _i_history(p, cx, cy, r, c, f):
        p.setBrush(f)
        p.drawEllipse(QPointF(cx, cy), r * 0.88, r * 0.88)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy - r * 0.5))
        p.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.38, cy + r * 0.2))

    @staticmethod
    def _i_trash(p, cx, cy, r, c, f):
        p.drawLine(QPointF(cx - r * 0.85, cy - r * 0.5), QPointF(cx + r * 0.85, cy - r * 0.5))
        p.drawLine(QPointF(cx - r * 0.3, cy - r * 0.5), QPointF(cx - r * 0.3, cy - r * 0.8))
        p.drawLine(QPointF(cx + r * 0.3, cy - r * 0.5), QPointF(cx + r * 0.3, cy - r * 0.8))
        p.drawLine(QPointF(cx - r * 0.3, cy - r * 0.8), QPointF(cx + r * 0.3, cy - r * 0.8))
        body = QPainterPath()
        body.moveTo(cx - r * 0.65, cy - r * 0.35)
        body.lineTo(cx - r * 0.5, cy + r * 0.85)
        body.lineTo(cx + r * 0.5, cy + r * 0.85)
        body.lineTo(cx + r * 0.65, cy - r * 0.35)
        p.setBrush(f)
        p.drawPath(body)

    @staticmethod
    def _i_open(p, cx, cy, r, c, f):
        p.drawRoundedRect(QRectF(cx - r * 0.85, cy - r * 0.55, r * 1.35, r * 1.4), 3, 3)
        p.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.85, cy - r * 0.85))
        p.drawLine(QPointF(cx + r * 0.3, cy - r * 0.85), QPointF(cx + r * 0.85, cy - r * 0.85))
        p.drawLine(QPointF(cx + r * 0.85, cy - r * 0.85), QPointF(cx + r * 0.85, cy - r * 0.3))

    @staticmethod
    def _i_reply(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx - r * 0.85, cy - r * 0.05)
        path.lineTo(cx - r * 0.2, cy - r * 0.7)
        path.moveTo(cx - r * 0.85, cy - r * 0.05)
        path.lineTo(cx - r * 0.2, cy + r * 0.6)
        path.moveTo(cx - r * 0.85, cy - r * 0.05)
        path.lineTo(cx + r * 0.35, cy - r * 0.05)
        path.cubicTo(cx + r * 0.85, cy - r * 0.05, cx + r * 0.85, cy + r * 0.8, cx + r * 0.35, cy + r * 0.8)
        p.drawPath(path)

    @staticmethod
    def _i_down(p, cx, cy, r, c, f):
        path = QPainterPath()
        path.moveTo(cx - r * 0.6, cy - r * 0.25)
        path.lineTo(cx, cy + r * 0.35)
        path.lineTo(cx + r * 0.6, cy - r * 0.25)
        p.drawPath(path)

    @staticmethod
    def _i_expand(p, cx, cy, r, c, f):
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            path = QPainterPath()
            path.moveTo(cx + sx * r * 0.85, cy + sy * r * 0.3)
            path.lineTo(cx + sx * r * 0.85, cy + sy * r * 0.85)
            path.lineTo(cx + sx * r * 0.3, cy + sy * r * 0.85)
            p.drawPath(path)


def vicon(name, color='#ffffff', size=18, badge=None):
    """QIcon из векторной иконки (для меню трея, списков и т. п.), с поддержкой HiDPI."""
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    VectorIcon.draw(p, name, QRectF(1, 1, size - 2, size - 2), QColor(color), QColor(badge) if badge else None)
    p.end()
    return QIcon(pm)


def dot_icon(color, size=14):
    """Круглая цветная метка (превью цвета темы / плеера в меню)."""
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(255, 255, 255, 70), 1))
    p.setBrush(QColor(color))
    p.drawEllipse(QRectF(1.5, 1.5, size - 3, size - 3))
    p.end()
    return QIcon(pm)
