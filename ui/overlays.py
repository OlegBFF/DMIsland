"""Полноэкранный оверлей выбора области (скриншот, OCR, QR, пипетка)."""
import math
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QPushButton, QWidget
from core.utils import clamp
from ui.themes import STYLE
from ui.widgets import fnt


# ==================== ОВЕРЛЕЙ ЗАХВАТА И РАЗМЕТКИ ====================
class SnapOverlay(QWidget):
    def __init__(s, pm, mode, host):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        s.pm = pm
        s.img = pm.toImage()
        s.mode = mode  # 'area' | 'pick' | 'ocr' | 'qr'
        s.host = host
        s.a = s.b = None
        s.selecting = False
        s.editing = False
        s.tool = 'arrow'
        s.color = QColor('#ff4d6d')
        s.shapes = []
        s.cur_pts = []
        s.mouse_pos = QPoint(0, 0)
        s.setMouseTracking(True)
        s.setCursor(Qt.CrossCursor)
        s.toolbar = QFrame(s)
        s.toolbar.setStyleSheet("QFrame{background:#18181c;border-radius:14px;border:1px solid rgba(255,255,255,35)}"
                                "QPushButton{color:#fff;background:rgba(255,255,255,18);border-radius:9px;padding:6px 10px}")
        tl = QHBoxLayout(s.toolbar)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(6)
        for tid, label in (('arrow', '↗ Стрелка'), ('rect', '▢ Рамка'), ('marker', '🖍 Маркер'),
                           ('text', 'T Текст'), ('blur', '▦ Размытие')):
            b = QPushButton(label)
            b.clicked.connect(lambda _=0, t=tid: setattr(s, 'tool', t))
            tl.addWidget(b)
        b_up = QPushButton('☁ Ссылка')
        b_up.clicked.connect(lambda: s.finish(upload=True))
        b_ok = QPushButton('✓ Готово')
        b_ok.setStyleSheet("background:#34c759;color:#fff;font-weight:600")
        b_ok.clicked.connect(lambda: s.finish(upload=False))
        tl.addWidget(b_up)
        tl.addWidget(b_ok)
        s.toolbar.hide()
        s.showFullScreen()

    def _crop_pm(s):
        if not s.a or not s.b:
            return QPixmap()
        r = QRect(s.a, s.b).normalized()
        k = s.pm.devicePixelRatio()
        base = s.pm.copy(QRect(int(r.x() * k), int(r.y() * k), int(r.width() * k), int(r.height() * k)))
        p = QPainter(base)
        p.setRenderHint(QPainter.Antialiasing)
        s._draw_shapes(p, offset=r.topLeft())
        p.end()
        return base

    def _draw_shapes(s, p, offset=QPoint(0, 0)):
        for kind, col, p1, p2, extra in s.shapes:
            a, b = p1 - offset, p2 - offset
            if kind == 'rect':
                p.setPen(QPen(col, 3))
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRect(a, b).normalized())
            elif kind == 'arrow':
                p.setPen(QPen(col, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawLine(a, b)
                ang = math.atan2(a.y() - b.y(), a.x() - b.x())
                for d in (-0.5, 0.5):
                    p.drawLine(b, QPoint(int(b.x() + 14 * math.cos(ang + d)), int(b.y() + 14 * math.sin(ang + d))))
            elif kind == 'marker':
                c = QColor(col)
                c.setAlpha(110)
                p.setPen(QPen(c, 14, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                for i in range(1, len(extra)):
                    p.drawLine(extra[i - 1] - offset, extra[i] - offset)
            elif kind == 'text' and extra:
                p.setPen(col)
                p.setFont(fnt(14, QFont.Bold))
                p.drawText(a, extra)
            elif kind == 'blur':
                br = QRect(a, b).normalized()
                if br.width() > 4 and br.height() > 4:
                    k = s.pm.devicePixelRatio()
                    src = QRect(int((br.x() + offset.x()) * k), int((br.y() + offset.y()) * k),
                                int(br.width() * k), int(br.height() * k))
                    sub = s.pm.copy(src).scaled(max(1, br.width() // 10), max(1, br.height() // 10),
                                                Qt.IgnoreAspectRatio, Qt.FastTransformation)
                    p.drawPixmap(br, sub.scaled(br.size(), Qt.IgnoreAspectRatio, Qt.FastTransformation))

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, s.pm)

        if s.mode == 'pick':
            mp = s.mouse_pos
            k = s.pm.devicePixelRatio()
            px, py = int(mp.x() * k), int(mp.y() * k)
            col = s.img.pixelColor(clamp(px, 0, s.img.width() - 1), clamp(py, 0, s.img.height() - 1))
            lx = mp.x() + 24 if mp.x() < s.width() - 180 else mp.x() - 164
            ly = mp.y() + 24 if mp.y() < s.height() - 180 else mp.y() - 164
            lr = QRectF(lx, ly, 140, 152)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1.5))
            p.setBrush(QColor(18, 18, 22, 240))
            p.drawRoundedRect(lr, 18, 18)
            sub = s.pm.copy(px - 4, py - 4, 9, 9).scaled(116, 96, Qt.IgnoreAspectRatio, Qt.FastTransformation)
            p.drawPixmap(int(lx + 12), int(ly + 10), sub)
            p.setPen(QPen(QColor('white'), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(int(lx + 64), int(ly + 52), 13, 11)
            p.setPen(QColor('white'))
            p.setFont(fnt(10, QFont.Bold))
            p.drawText(QRectF(lx + 12, ly + 110, 116, 18), Qt.AlignCenter, col.name().upper())
            p.setPen(QColor(255, 255, 255, 160))
            p.setFont(fnt(8.5))
            p.drawText(QRectF(lx + 12, ly + 127, 116, 18), Qt.AlignCenter, f"rgb({col.red()},{col.green()},{col.blue()})")
            return

        d = QPainterPath()
        d.addRect(QRectF(s.rect()))
        if s.a and s.b:
            r = QRect(s.a, s.b).normalized()
            d.addRect(QRectF(r))
            p.fillPath(d, QColor(0, 0, 0, 130))
            s._draw_shapes(p)
            p.setPen(QPen(STYLE['acc'], 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
        else:
            p.fillPath(d, QColor(0, 0, 0, 110))

    def keyPressEvent(s, e):
        if e.key() == Qt.Key_Escape:
            s.close()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and s.editing:
            s.finish(False)

    def mousePressEvent(s, e):
        pt = e.position().toPoint()
        if s.mode == 'pick':
            k = s.pm.devicePixelRatio()
            c = s.img.pixelColor(int(pt.x() * k), int(pt.y() * k))
            s.close()
            s.host.on_color_picked(c)
            return
        if not s.editing:
            s.a = s.b = pt
            s.selecting = True
        else:
            if s.tool == 'text':
                txt, ok = QInputDialog.getText(s, 'Текст на скриншоте', 'Введите подпись:')
                if ok and txt:
                    s.shapes.append(('text', s.color, pt, pt, txt))
                    s.update()
            else:
                s.cur_pts = [pt]
                s.shapes.append([s.tool, s.color, pt, pt, s.cur_pts])

    def mouseMoveEvent(s, e):
        pt = e.position().toPoint()
        s.mouse_pos = pt
        if s.mode == 'pick':
            s.update()
            return
        if s.selecting:
            s.b = pt
            s.update()
        elif s.editing and (e.buttons() & Qt.LeftButton) and s.shapes:
            s.shapes[-1][3] = pt
            if s.tool == 'marker':
                s.cur_pts.append(pt)
            s.update()

    def mouseReleaseEvent(s, e):
        if s.selecting:
            s.selecting = False
            r = QRect(s.a, s.b).normalized()
            if r.width() < 8 or r.height() < 8:
                s.close()
                return
            if s.mode in ('ocr', 'qr', 'ctx_shot', 'ctx_ocr'):
                pm = s._crop_pm()
                s.close()
                if s.mode in ('ctx_shot', 'ctx_ocr'):
                    s.host.on_ctx_crop(s.mode, pm)              # область для чата с ИИ
                elif s.mode == 'ocr':
                    s.host.run_ocr_ram(pm)
                else:
                    s.host.run_qr_ram(pm)
                return
            s.editing = True
            s.toolbar.adjustSize()
            tx = clamp(r.right() - s.toolbar.width(), 10, s.width() - s.toolbar.width() - 10)
            ty = r.bottom() + 10 if r.bottom() + 60 < s.height() else max(10, r.top() - 54)
            s.toolbar.move(int(tx), int(ty))
            s.toolbar.show()
            s.update()

    def finish(s, upload=False):
        pm = s._crop_pm()
        s.close()
        if not pm.isNull():
            s.host.save_shot(pm, upload=upload)
