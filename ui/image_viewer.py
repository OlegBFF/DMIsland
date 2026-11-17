"""Просмотр изображения поверх экрана: скриншот из чата, картинка из уведомления. Клик или Esc закрывает."""
import os
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget
from ui.widgets import fnt

_open = []          # живые окна просмотра (иначе их соберёт сборщик мусора)


class ImageViewer(QWidget):
    def __init__(s, pm: QPixmap, title: str = '', path: str = ''):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        s.setAttribute(Qt.WA_TranslucentBackground)
        s.setAttribute(Qt.WA_DeleteOnClose)
        s.pm, s.title, s.path = pm, title, path
        scr = QGuiApplication.screenAt(QGuiApplication.primaryScreen().geometry().center()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        s.setGeometry(g)
        s.setFocusPolicy(Qt.StrongFocus)
        s.hover = ''
        s.setMouseTracking(True)
        _open.append(s)
        s.show()
        s.raise_()
        s.activateWindow()
        s.setFocus()

    def _img_rect(s) -> QRectF:
        w, h = s.width(), s.height()
        dpr = s.pm.devicePixelRatio() or 1.0
        iw, ih = s.pm.width() / dpr, s.pm.height() / dpr
        k = min((w * 0.84) / iw, (h * 0.78) / ih, 2.0)
        rw, rh = iw * k, ih * k
        return QRectF((w - rw) / 2, (h - rh) / 2 - 10, rw, rh)

    def _btns(s):
        r = s._img_rect()
        y = r.bottom() + 16
        return {'copy': QRectF(r.center().x() - 112, y, 104, 34), 'open': QRectF(r.center().x() + 8, y, 104, 34)}

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(s.rect(), QColor(0, 0, 0, 170))
        r = s._img_rect()
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.save()
        p.setClipPath(path)
        p.drawPixmap(r.toRect(), s.pm)
        p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 14, 14)
        if s.title:
            p.setPen(QColor(255, 255, 255, 200))
            p.setFont(fnt(10.5, QFont.DemiBold))
            p.drawText(QRectF(r.left(), r.top() - 30, r.width(), 24), Qt.AlignVCenter | Qt.AlignLeft, s.title)
        for k, b in s._btns().items():
            if k == 'open' and not s.path:
                continue
            hv = s.hover == k
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 60 if hv else 34))
            p.drawRoundedRect(b, 17, 17)
            p.setPen(QColor('white'))
            p.setFont(fnt(10, QFont.DemiBold))
            p.drawText(b, Qt.AlignCenter, 'Копировать' if k == 'copy' else 'Открыть файл')

    def mouseMoveEvent(s, e):
        h = next((k for k, b in s._btns().items() if b.contains(e.position()) and (k != 'open' or s.path)), '')
        if h != s.hover:
            s.hover = h
            s.setCursor(Qt.PointingHandCursor if h else Qt.ArrowCursor)
            s.update()

    def mousePressEvent(s, e):
        h = s.hover
        if h == 'copy':
            QGuiApplication.clipboard().setPixmap(s.pm)
        elif h == 'open' and s.path and os.path.exists(s.path):
            try:
                os.startfile(s.path)
            except OSError:
                pass
        s.close()

    def keyPressEvent(s, e):
        if e.key() == Qt.Key_Escape:
            s.close()

    def closeEvent(s, e):
        if s in _open:
            _open.remove(s)
        super().closeEvent(e)
