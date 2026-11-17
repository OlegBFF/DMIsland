"""Виджеты диалога с ИИ: пузыри сообщений (Markdown, потоковый вывод), строка ввода, вложения, пустое состояние, шапка."""
import math
import time
from PySide6.QtCore import QPointF, QRectF, QSize, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap, QRadialGradient,
    QTextBlockFormat, QTextCharFormat, QTextCursor, QTextFormat,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QStackedWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)
from ui.icons import VectorIcon
from ui.themes import STYLE, on_acc
from ui.widgets import IconBtn, fnt

ATTACH_ICON = {'shot': 'image', 'ocr': 'ocr', 'clip': 'clip', 'img': 'image'}


def fg_col(a=255):
    c = QColor('#141416') if STYLE['light'] else QColor('white')
    c.setAlpha(a)
    return c


def surface(a_dark=16, a_light=11):
    return QColor(0, 0, 0, a_light * 2) if STYLE['light'] else QColor(255, 255, 255, a_dark)


def line_col():
    return QColor(0, 0, 0, 30) if STYLE['light'] else QColor(255, 255, 255, 26)


def rgba_css(c: QColor) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"


def rgb_css(c: QColor) -> str:
    """Цвет без «#fff» и «rgba(255,255,255,…»: так его не перекрасит retint_inline светлых тем."""
    return f"rgb({c.red()},{c.green()},{c.blue()})"


# ==================== ПУЗЫРЬ СООБЩЕНИЯ ====================
class AttachThumb(QWidget):
    """Миниатюра вложения внутри пузыря пользователя: скриншот — превью, текст/буфер — компактная плашка."""
    clicked = Signal(str)

    def __init__(s, att: dict):
        super().__init__()
        s.att, s.pm = att, None
        path = att.get('path')
        if att.get('kind') in ('shot', 'img') and path:
            pm = QPixmap(path)
            if not pm.isNull():
                s.pm = pm.scaled(176, 108, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if s.pm is not None:
            s.setFixedSize(s.pm.width(), s.pm.height())
            s.setCursor(Qt.PointingHandCursor)
        else:
            fm = QFontMetrics(fnt(9.2, QFont.DemiBold))
            s.setFixedSize(min(fm.horizontalAdvance(att.get('label', '')) + 38, 220), 24)

    def mousePressEvent(s, e):
        if s.pm is not None and s.att.get('path'):
            s.clicked.emit(s.att['path'])

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(s.rect())
        if s.pm is not None:
            path = QPainterPath()
            path.addRoundedRect(r, 10, 10)
            p.setClipPath(path)
            p.drawPixmap(0, 0, s.pm)
            p.setClipping(False)
            p.setPen(QPen(QColor(255, 255, 255, 60), 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), 10, 10)
            return
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 55))
        p.drawRoundedRect(r, 12, 12)
        VectorIcon.draw(p, ATTACH_ICON.get(s.att.get('kind'), 'clip'), QRectF(7, 4, 16, 16), QColor(255, 255, 255, 230))
        p.setPen(QColor(255, 255, 255, 235))
        p.setFont(fnt(9.2, QFont.DemiBold))
        p.drawText(QRectF(28, 0, r.width() - 34, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(s.att.get('label', ''), Qt.ElideRight, int(r.width() - 36)))


class Bubble(QWidget):
    """role: user | assistant | error. Ассистент — Markdown, пользователь и ошибка — простой текст."""
    linkClicked = Signal(str)
    imageClicked = Signal(str)
    copyRequested = Signal(str)

    PAD_X, PAD_Y = 14, 10

    def __init__(s, role: str, text: str = '', attach=None):
        super().__init__()
        s.role, s.text, s.thinking = role, text or '', False
        s.setAttribute(Qt.WA_StyledBackground, False)
        s.tb = QTextBrowser(s)
        s.tb.setObjectName('bubbleText')
        s.tb.setProperty('keep_colors', True)
        s.tb.setFrameShape(QFrame.NoFrame)
        s.tb.setOpenLinks(False)
        s.tb.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        s.tb.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        s.tb.document().setDocumentMargin(0)
        s.tb.setViewportMargins(0, 0, 0, 0)
        s.tb.anchorClicked.connect(lambda u: s.linkClicked.emit(u.toString()))
        s.thumbs = []
        s.thumb_box = QWidget(s)
        tl = QHBoxLayout(s.thumb_box)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        for a in attach or []:
            t = AttachThumb(a)
            t.clicked.connect(s.imageClicked)
            tl.addWidget(t)
            s.thumbs.append(t)
        tl.addStretch()
        s.thumb_box.setVisible(bool(s.thumbs))
        s.btn_copy = IconBtn('copy', 'Копировать ответ', 24, fn=lambda: s.copyRequested.emit(s.text))
        s.btn_copy.setParent(s)
        s.btn_copy.hide()
        s.dots_timer = QTimer(s)
        s.dots_timer.setInterval(60)
        s.dots_timer.timeout.connect(s.update)
        s.max_w = 480
        s.link_color = QColor(STYLE['acc'])
        s.restyle()
        s.set_text(s.text)

    # ---------- оформление ----------
    def text_color(self) -> QColor:
        return on_acc(STYLE['acc']) if self.role == 'user' else fg_col()

    def restyle(s):
        col = s.text_color()
        s.tb.setStyleSheet(f"#bubbleText{{background:transparent;border:0;padding:0;color:{rgb_css(col)};"
                           f"selection-background-color:{rgba_css(QColor(STYLE['acc']))};}}")
        acc = STYLE['acc']
        code_bg = QColor(0, 0, 0, 70) if s.role == 'user' else (QColor(0, 0, 0, 24) if STYLE['light'] else QColor(0, 0, 0, 90))
        link_c = QColor(acc).lighter(135) if not STYLE['light'] else QColor(acc).darker(120)
        link_c = link_c if s.role != 'user' else col
        link = rgb_css(link_c)
        s.link_color = link_c
        pal = s.tb.palette()
        pal.setColor(QPalette.Link, link_c)                 # ссылки из Markdown берут цвет из палитры, не из таблицы стилей
        pal.setColor(QPalette.LinkVisited, link_c)
        s.tb.setPalette(pal)
        s.tb.document().setDefaultStyleSheet(
            f"a{{color:{link};text-decoration:none}} code{{font-family:Consolas,'Cascadia Mono',monospace;background-color:{rgba_css(code_bg)}}}"
            f"h1,h2,h3{{margin:6px 0 2px 0}} li{{margin:1px 0}}")
        if s.text:
            s.set_text(s.text, refit=False)
        s.update()

    def set_text(s, text: str, refit=True):
        s.text = text
        doc = s.tb.document()
        if s.role == 'assistant':
            doc.setMarkdown(text)
            s._style_code_blocks()
        else:
            doc.setPlainText(text)
        s.tb.setVisible(bool(text) and not s.thinking)
        if refit:
            s.fit(s.max_w)

    def _style_code_blocks(s):
        """Блоки кода из Markdown: фон, отступы и перенос строк (без горизонтальной прокрутки в пузыре)."""
        doc = s.tb.document()
        bg = QColor(0, 0, 0, 20) if STYLE['light'] else QColor(0, 0, 0, 95)
        blk = doc.begin()
        while blk.isValid():
            bf = blk.blockFormat()
            is_code = bf.hasProperty(QTextFormat.BlockCodeFence) or bf.hasProperty(QTextFormat.BlockCodeLanguage)
            if is_code:
                cur = QTextCursor(blk)
                nf = QTextBlockFormat(bf)
                nf.setBackground(bg)
                nf.setLeftMargin(8)
                nf.setRightMargin(8)
                nf.setTopMargin(2)
                nf.setBottomMargin(2)
                nf.setNonBreakableLines(False)
                cur.setBlockFormat(nf)
            blk = blk.next()
        s._color_links()

    def _color_links(s):
        """Markdown-ссылки получают цвет из палитры Qt (синий) — перекрашиваем под тему."""
        col = s.link_color
        doc = s.tb.document()
        blk = doc.begin()
        while blk.isValid():
            it = blk.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().isAnchor():
                    cur = QTextCursor(doc)
                    cur.setPosition(frag.position())
                    cur.setPosition(frag.position() + frag.length(), QTextCursor.KeepAnchor)
                    f = QTextCharFormat()
                    f.setForeground(col)
                    f.setFontUnderline(True)
                    cur.mergeCharFormat(f)
                it += 1
            blk = blk.next()

    def set_thinking(s, on: bool):
        s.thinking = on
        s.tb.setVisible(bool(s.text) and not on)
        if on:
            s.dots_timer.start()
        else:
            s.dots_timer.stop()
        s.fit(s.max_w)

    # ---------- размер ----------
    def fit(s, max_w: int):
        s.max_w = max_w
        px, py = s.PAD_X, s.PAD_Y
        inner = max(max_w - 2 * px, 60)
        thumbs_w = sum(t.width() for t in s.thumbs) + 6 * max(len(s.thumbs) - 1, 0)
        thumbs_h = max((t.height() for t in s.thumbs), default=0)
        if s.thinking or not s.text:
            tw, th = (46 if s.thinking else 0), (16 if s.thinking else 0)
        else:
            doc = s.tb.document()
            doc.setTextWidth(inner)
            tw = min(math.ceil(doc.idealWidth()) + 2, inner)
            doc.setTextWidth(tw)
            th = math.ceil(doc.size().height()) + 1
            s.tb.setFixedSize(int(tw), int(th))
        w = max(tw, thumbs_w, 46 if s.role == 'assistant' else 0)
        gap = 8 if (s.thumbs and th) else 0
        s.tb.move(px, py)
        s.thumb_box.setGeometry(px, py + th + gap, int(max(thumbs_w, 1)), int(thumbs_h))
        s.setFixedSize(int(w + 2 * px), int(py * 2 + th + gap + thumbs_h))
        s.btn_copy.move(s.width() - 28, 4)

    # ---------- события ----------
    def enterEvent(s, e):
        if s.role == 'assistant' and s.text and not s.thinking:
            s.btn_copy.show()
            s.btn_copy.raise_()

    def leaveEvent(s, e):
        s.btn_copy.hide()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(s.rect()).adjusted(.5, .5, -.5, -.5)
        big, small = 17.0, 5.0
        path = QPainterPath()
        # скругления: у «хвоста» (нижний угол со стороны автора) — маленькое
        tl, tr, br, bl = big, big, (small if s.role == 'user' else big), (small if s.role != 'user' else big)
        path.moveTo(r.left() + tl, r.top())
        path.lineTo(r.right() - tr, r.top())
        path.quadTo(r.right(), r.top(), r.right(), r.top() + tr)
        path.lineTo(r.right(), r.bottom() - br)
        path.quadTo(r.right(), r.bottom(), r.right() - br, r.bottom())
        path.lineTo(r.left() + bl, r.bottom())
        path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - bl)
        path.lineTo(r.left(), r.top() + tl)
        path.quadTo(r.left(), r.top(), r.left() + tl, r.top())
        if s.role == 'user':
            acc = QColor(STYLE['acc'])
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, acc.lighter(112))
            g.setColorAt(1, acc.darker(112))
            p.fillPath(path, g)
        elif s.role == 'error':
            p.fillPath(path, QColor(255, 69, 58, 40))
            p.setPen(QPen(QColor(255, 69, 58, 120), 1))
            p.drawPath(path)
        else:
            p.fillPath(path, surface(17, 12))
            p.setPen(QPen(line_col(), 1))
            p.drawPath(path)
        if s.thinking:
            t = time.monotonic()
            cy = s.height() / 2
            for i in range(3):
                ph = (math.sin(t * 5.5 - i * 0.9) + 1) / 2
                c = fg_col(int(80 + 150 * ph))
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawEllipse(QPointF(s.PAD_X + 6 + i * 13, cy - 2.5 * ph), 3.2 + 0.8 * ph, 3.2 + 0.8 * ph)


class ActionPill(QWidget):
    """Строка-результат команды: «✓ Громкость: 30%»."""

    def __init__(s, text: str, ok: bool = True):
        super().__init__()
        s.text, s.ok = text, ok
        fm = QFontMetrics(fnt(9.6, QFont.DemiBold))
        s.setFixedSize(min(fm.horizontalAdvance(text) + 46, 460), 28)

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        col = QColor('#34c759') if s.ok else QColor('#ff9f0a')
        bg = QColor(col)
        bg.setAlpha(34)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 90), 1))
        p.setBrush(bg)
        r = QRectF(s.rect()).adjusted(.5, .5, -.5, -.5)
        p.drawRoundedRect(r, 14, 14)
        VectorIcon.draw(p, 'check' if s.ok else 'info', QRectF(9, 6, 16, 16), col)
        p.setPen(fg_col(225))
        p.setFont(fnt(9.6, QFont.DemiBold))
        p.drawText(QRectF(30, 0, r.width() - 36, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(s.text, Qt.ElideRight, int(r.width() - 38)))


class AvatarDot(QWidget):
    """Значок ИИ рядом с ответом."""

    def __init__(s):
        super().__init__()
        s.setFixedSize(28, 28)

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        VectorIcon.draw(p, 'spark', QRectF(1, 1, 26, 26), on_acc(STYLE['acc']), QColor(STYLE['acc']))


# ==================== ЛЕНТА СООБЩЕНИЙ ====================
class Suggest(QPushButton):
    """Подсказка в пустом чате: нажатие запускает фразу или подставляет шаблон."""

    def __init__(s, icon: str, text: str, run: bool):
        super().__init__()
        s.icon_name, s.label, s.run = icon, text, run
        s.setCursor(Qt.PointingHandCursor)
        fm = QFontMetrics(fnt(10, QFont.DemiBold))
        s.setFixedSize(fm.horizontalAdvance(text) + 64, 36)

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        hv = s.underMouse()
        p.setPen(QPen(line_col(), 1))
        p.setBrush(surface(30 if hv else 16, 20 if hv else 11))
        r = QRectF(s.rect()).adjusted(.5, .5, -.5, -.5)
        p.drawRoundedRect(r, 18, 18)
        VectorIcon.draw(p, s.icon_name, QRectF(12, 9, 18, 18), QColor(STYLE['acc']).lighter(125 if not STYLE['light'] else 100))
        p.setPen(fg_col(235))
        p.setFont(fnt(10, QFont.DemiBold))
        p.drawText(QRectF(38, 0, r.width() - 42, r.height()), Qt.AlignVCenter | Qt.AlignLeft, s.label)


class EmptyState(QWidget):
    chosen = Signal(str, bool)

    SUGGESTIONS = (
        ('image', 'Что на экране?', 'Что сейчас на экране? Опиши коротко и подскажи, что можно сделать.', True),
        ('clip', 'Объясни буфер', 'Объясни, что в буфере обмена', True),
        ('ocr', 'Текст с экрана', 'распознай текст с экрана', True),
        ('sys', 'Громкость 30%', 'уменьши громкость до 30%', True),
        ('notes', 'Напомни через 15 минут…', 'напомни через 15 минут ', False),
        ('link', 'Открой YouTube', 'открой ютуб', True),
    )

    def __init__(s):
        super().__init__()
        v = QVBoxLayout(s)
        v.setContentsMargins(10, 4, 10, 4)
        v.addStretch(2)
        s.title = QLabel('Чем помочь?')
        s.title.setAlignment(Qt.AlignCenter)
        s.title.setProperty('keep_colors', True)
        s.sub = QLabel('Спросите что угодно, покажите экран или дайте команду — текстом или голосом')
        s.sub.setAlignment(Qt.AlignCenter)
        s.sub.setWordWrap(True)
        s.icon_box = QWidget()
        s.icon_box.setFixedHeight(76)
        s.icon_box.paintEvent = s._paint_icon
        v.addWidget(s.icon_box)
        v.addWidget(s.title)
        v.addWidget(s.sub)
        v.addSpacing(10)
        rows = QVBoxLayout()
        rows.setSpacing(8)
        for chunk in (s.SUGGESTIONS[:3], s.SUGGESTIONS[3:]):
            h = QHBoxLayout()
            h.setSpacing(8)
            h.addStretch()
            for ic, label, text, run in chunk:
                b = Suggest(ic, label, run)
                b.clicked.connect(lambda _=False, t=text, r=run: s.chosen.emit(t, r))
                h.addWidget(b)
            h.addStretch()
            rows.addLayout(h)
        v.addLayout(rows)
        v.addStretch(3)
        s.restyle()

    def restyle(s):
        s.title.setStyleSheet(f"font-size:19px;font-weight:700;background:transparent;border:0;color:{rgb_css(fg_col())}")
        s.sub.setStyleSheet(f"font-size:11.5px;background:transparent;border:0;color:{rgba_css(fg_col(140))}")

    def _paint_icon(s, e):
        p = QPainter(s.icon_box)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = s.icon_box.width() / 2, s.icon_box.height() / 2
        acc = QColor(STYLE['acc'])
        g = QRadialGradient(QPointF(cx, cy), 46)
        c0 = QColor(acc)
        c0.setAlpha(80)
        c1 = QColor(acc)
        c1.setAlpha(0)
        g.setColorAt(0, c0)
        g.setColorAt(1, c1)
        p.fillRect(s.icon_box.rect(), g)
        pulse = 1.0 + 0.04 * math.sin(time.monotonic() * 2.0)
        VectorIcon.draw(p, 'spark', QRectF(cx - 25 * pulse, cy - 25 * pulse, 50 * pulse, 50 * pulse), on_acc(acc), acc)


class ChatView(QStackedWidget):
    """Пустое состояние + прокручиваемая лента пузырей. Сообщения добавляются, ответ ИИ дописывается на месте."""
    suggestion = Signal(str, bool)
    linkClicked = Signal(str)
    imageClicked = Signal(str)
    copyRequested = Signal(str)

    def __init__(s):
        super().__init__()
        s.empty = EmptyState()
        s.empty.chosen.connect(s.suggestion)
        s.addWidget(s.empty)
        s.scroll = QScrollArea()
        s.scroll.setWidgetResizable(True)
        s.scroll.setFrameShape(QFrame.NoFrame)
        s.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        s.scroll.setStyleSheet('QScrollArea{background:transparent;border:0}')
        s.scroll.viewport().setAutoFillBackground(False)
        s.body = QWidget()
        s.body.setStyleSheet('background:transparent')
        s.col = QVBoxLayout(s.body)
        s.col.setContentsMargins(2, 6, 10, 6)
        s.col.setSpacing(8)
        s.col.addStretch()
        s.scroll.setWidget(s.body)
        s.addWidget(s.scroll)
        s.rows, s.stick = [], True
        s.scroll.verticalScrollBar().valueChanged.connect(s._on_scroll)
        s.scroll.verticalScrollBar().rangeChanged.connect(lambda *_: s._after_range())
        s._refit_t = QTimer(s)
        s._refit_t.setSingleShot(True)
        s._refit_t.setInterval(30)
        s._refit_t.timeout.connect(s.refit)

    # ---------- прокрутка ----------
    def _on_scroll(s, v):
        sb = s.scroll.verticalScrollBar()
        s.stick = v >= sb.maximum() - 36

    def _after_range(s):
        if s.stick:
            sb = s.scroll.verticalScrollBar()
            sb.setValue(sb.maximum())

    def to_bottom(s):
        s.stick = True
        QTimer.singleShot(0, s._after_range)

    # ---------- содержимое ----------
    def bubble_width(s) -> int:
        avail = s.scroll.viewport().width() - 14
        return max(160, min(int(avail * 0.84), 560)) if avail > 0 else 480

    def clear(s):
        for row, _ in s.rows:
            s.col.removeWidget(row)
            row.deleteLater()
        s.rows = []
        s.setCurrentWidget(s.empty)

    def _row(s, widget, align):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        return row, h

    def add(s, role: str, text: str = '', attach=None):
        """Возвращает виджет-«ручку» (Bubble или ActionPill)."""
        s.setCurrentWidget(s.scroll)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        if role == 'action':
            w = ActionPill(text, ok=True if attach is None else bool(attach))
            h.addStretch()
            h.addWidget(w)
            h.addStretch()
        else:
            w = Bubble(role, text, attach if role == 'user' else None)
            w.linkClicked.connect(s.linkClicked)
            w.imageClicked.connect(s.imageClicked)
            w.copyRequested.connect(s.copyRequested)
            w.fit(s.bubble_width())
            if role == 'user':
                h.addStretch()
                h.addWidget(w)
            else:
                av = AvatarDot()
                h.addWidget(av, 0, Qt.AlignTop)
                h.addWidget(w)
                h.addStretch()
        s.col.insertWidget(s.col.count() - 1, row)
        s.rows.append((row, w))
        s.to_bottom()
        return w

    def last(s):
        return s.rows[-1][1] if s.rows else None

    def refit(s):
        bw = s.bubble_width()
        for _, w in s.rows:
            if isinstance(w, Bubble):
                w.fit(bw)

    def resizeEvent(s, e):
        super().resizeEvent(e)
        s._refit_t.start()

    def restyle(s):
        s.empty.restyle()
        for _, w in s.rows:
            if isinstance(w, Bubble):
                w.restyle()
        s.refit()
        s.update()


# ==================== СТРОКА ВВОДА ====================
class ChatInput(QPlainTextEdit):
    """Многострочное поле: Enter — отправить, Shift+Enter — новая строка, Esc — свернуть остров."""
    submitted = Signal()
    escaped = Signal()
    focusChanged = Signal(bool)

    def __init__(s):
        super().__init__()
        s.setFrameShape(QFrame.NoFrame)
        s.setStyleSheet('QPlainTextEdit{background:transparent;border:0;padding:0}')
        s.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        s.document().setDocumentMargin(2)
        s.document().documentLayout().documentSizeChanged.connect(lambda _=None: s._autosize())
        s._autosize()

    def _autosize(s):
        lines = s.document().size().height()
        h = int(max(26, min(lines + 4, 112)))
        if h != s.height():
            s.setFixedHeight(h)

    def keyPressEvent(s, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and not (e.modifiers() & Qt.ShiftModifier):
            s.submitted.emit()
            return
        if e.key() == Qt.Key_Escape:
            s.escaped.emit()
            return
        super().keyPressEvent(e)

    def insertFromMimeData(s, src):
        s.insertPlainText(src.text())           # без форматирования из чужих приложений

    def focusInEvent(s, e):
        super().focusInEvent(e)
        s.focusChanged.emit(True)

    def focusOutEvent(s, e):
        super().focusOutEvent(e)
        s.focusChanged.emit(False)


class AttachChip(QWidget):
    removed = Signal(int)

    def __init__(s, idx: int, att: dict):
        super().__init__()
        s.idx, s.att, s.hover_x, s.pm = idx, att, False, None
        path = att.get('path')
        if path and att.get('kind') in ('shot', 'img'):
            pm = QPixmap(path)
            if not pm.isNull():
                s.pm = pm.scaled(44, 44, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation).copy(0, 0, 22, 22)
        s.setMouseTracking(True)
        s.setCursor(Qt.PointingHandCursor)
        s.setToolTip(att.get('tip', ''))
        fm = QFontMetrics(fnt(9.4, QFont.DemiBold))
        s.setFixedSize(min(fm.horizontalAdvance(att.get('label', '')) + 64, 240), 30)

    def mouseMoveEvent(s, e):
        hx = e.position().x() > s.width() - 26
        if hx != s.hover_x:
            s.hover_x = hx
            s.update()

    def leaveEvent(s, e):
        s.hover_x = False
        s.update()

    def mousePressEvent(s, e):
        if e.position().x() > s.width() - 26:
            s.removed.emit(s.idx)

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(s.rect()).adjusted(.5, .5, -.5, -.5)
        acc = QColor(STYLE['acc'])
        bg = QColor(acc)
        bg.setAlpha(36)
        p.setPen(QPen(QColor(acc.red(), acc.green(), acc.blue(), 110), 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 15, 15)
        if s.pm is not None:
            path = QPainterPath()
            path.addRoundedRect(QRectF(5, 4, 22, 22), 6, 6)
            p.save()
            p.setClipPath(path)
            p.drawPixmap(5, 4, s.pm)
            p.restore()
        else:
            VectorIcon.draw(p, ATTACH_ICON.get(s.att.get('kind'), 'clip'), QRectF(8, 7, 16, 16), acc.lighter(130) if not STYLE['light'] else acc.darker(120))
        p.setPen(fg_col(235))
        p.setFont(fnt(9.4, QFont.DemiBold))
        p.drawText(QRectF(32, 0, r.width() - 58, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(s.att.get('label', ''), Qt.ElideRight, int(r.width() - 60)))
        if s.hover_x:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 40) if not STYLE['light'] else QColor(0, 0, 0, 30))
            p.drawEllipse(QRectF(r.width() - 24, 6, 18, 18))
        VectorIcon.draw(p, 'close', QRectF(r.width() - 23, 7, 16, 16), fg_col(190 if s.hover_x else 140))


class InputFrame(QWidget):
    """Скруглённая «капсула» поля ввода: рамка подсвечивается акцентом, пока в поле фокус."""

    def __init__(s):
        super().__init__()
        s.focused = False
        s.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(s.rect()).adjusted(.5, .5, -.5, -.5)
        rad = min(22.0, r.height() / 2)
        p.setBrush(surface(17, 12))
        if s.focused:
            acc = QColor(STYLE['acc'])
            acc.setAlpha(170)
            p.setPen(QPen(acc, 1.4))
        else:
            p.setPen(QPen(line_col(), 1))
        p.drawRoundedRect(r, rad, rad)


class Composer(QWidget):
    submitted = Signal()
    stopClicked = Signal()
    micClicked = Signal()
    attachClicked = Signal()
    attachRemoved = Signal(int)
    escaped = Signal()

    PLACEHOLDER = 'Спросите ИИ или дайте команду…'

    def __init__(s):
        super().__init__()
        s.busy = False
        v = QVBoxLayout(s)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        s.chips_box = QWidget()
        s.chips = QHBoxLayout(s.chips_box)
        s.chips.setContentsMargins(4, 0, 0, 0)
        s.chips.setSpacing(6)
        s.chips.addStretch()
        s.chips_box.hide()
        v.addWidget(s.chips_box)
        s.frame = InputFrame()
        h = QHBoxLayout(s.frame)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)
        s.b_attach = IconBtn('plus', 'Добавить контекст: экран, текст с экрана, буфер', 32, fn=s.attachClicked.emit)
        s.ed = ChatInput()
        s.ed.setPlaceholderText(s.PLACEHOLDER)
        s.ed.submitted.connect(s.submitted)
        s.ed.escaped.connect(s.escaped)
        s.ed.focusChanged.connect(s._focus)
        s.b_mic = IconBtn('voice', 'Сказать голосом (команда или вопрос)', 32, fn=s.micClicked.emit)
        s.b_send = IconBtn('send', 'Отправить (Enter)', 32, accent=True, fn=s._send_or_stop)
        h.addWidget(s.b_attach, 0, Qt.AlignBottom)
        h.addWidget(s.ed, 1, Qt.AlignVCenter)
        h.addWidget(s.b_mic, 0, Qt.AlignBottom)
        h.addWidget(s.b_send, 0, Qt.AlignBottom)
        v.addWidget(s.frame)
        s.atts = []

    def _focus(s, on):
        s.frame.focused = on
        s.frame.update()

    def _send_or_stop(s):
        (s.stopClicked if s.busy else s.submitted).emit()

    # ---------- состояние ----------
    def text(s) -> str:
        return s.ed.toPlainText().strip()

    def set_text(s, t: str):
        s.ed.setPlainText(t)
        s.ed.moveCursor(QTextCursor.End)

    def clear(s):
        s.ed.clear()

    def set_busy(s, busy: bool):
        s.busy = busy
        s.b_send.set_icon('stop' if busy else 'send')
        s.b_send.setToolTip('Остановить' if busy else 'Отправить (Enter)')

    def set_listening(s, on: bool):
        s.b_mic.set_active('#ff453a' if on else None)
        s.ed.setPlaceholderText('Слушаю… говорите' if on else s.PLACEHOLDER)

    def set_attachments(s, atts):
        s.atts = list(atts)
        while s.chips.count() > 1:
            it = s.chips.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for i, a in enumerate(s.atts):
            c = AttachChip(i, a)
            c.removed.connect(s.attachRemoved)
            s.chips.insertWidget(s.chips.count() - 1, c)
        s.chips_box.setVisible(bool(s.atts))

    def focus(s):
        s.ed.setFocus()


# ==================== ШАПКА ====================
class ElidedLabel(QLabel):
    def paintEvent(s, e):
        p = QPainter(s)
        p.setFont(s.font())
        p.setPen(s.palette().color(s.foregroundRole()))
        p.drawText(s.rect(), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(s.font()).elidedText(s.text(), Qt.ElideRight, s.width()))


class ChatHeader(QWidget):
    newClicked = Signal()
    historyClicked = Signal()
    closeClicked = Signal()
    settingsClicked = Signal()

    def __init__(s):
        super().__init__()
        s.title, s.sub = 'ИИ-ассистент', ''
        s.setFixedHeight(40)
        h = QHBoxLayout(s)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addSpacing(40)
        h.addStretch()
        s.b_new = IconBtn('plus', 'Новый диалог', 30, fn=s.newClicked.emit)
        s.b_hist = IconBtn('history', 'История диалогов', 30, fn=s.historyClicked.emit)
        s.b_close = IconBtn('down', 'Свернуть остров (Esc)', 30, fn=s.closeClicked.emit)
        for b in (s.b_new, s.b_hist, s.b_close):
            h.addWidget(b)

    def set_info(s, title: str, sub: str):
        s.title, s.sub = title or 'Новый диалог', sub
        s.update()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        VectorIcon.draw(p, 'spark', QRectF(0, 4, 32, 32), on_acc(STYLE['acc']), QColor(STYLE['acc']))
        right = 3 * 34 + 8
        w = max(s.width() - 44 - right, 40)
        p.setPen(fg_col())
        p.setFont(fnt(11.2, QFont.DemiBold))
        p.drawText(QRectF(42, 2, w, 20), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(s.title, Qt.ElideRight, int(w)))
        p.setPen(fg_col(130))
        p.setFont(fnt(8.8))
        p.drawText(QRectF(42, 21, w, 16), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(s.sub, Qt.ElideRight, int(w)))


class NoticeBar(QWidget):
    """Полоска-подсказка над лентой («нет API-ключа»). Кнопка открывает настройки."""
    clicked = Signal()

    def __init__(s):
        super().__init__()
        s.text, s.btn = '', 'Настроить'
        s.setFixedHeight(32)
        s.setCursor(Qt.PointingHandCursor)
        s.hide()

    def set_notice(s, text: str, btn: str = 'Настроить'):
        s.text, s.btn = text, btn
        s.setVisible(bool(text))
        s.update()

    def mousePressEvent(s, e):
        s.clicked.emit()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(s.rect()).adjusted(.5, .5, -.5, -.5)
        col = QColor('#ff9f0a')
        bg = QColor(col)
        bg.setAlpha(30)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 90), 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 12, 12)
        VectorIcon.draw(p, 'info', QRectF(10, 8, 16, 16), col)
        p.setPen(fg_col(225))
        p.setFont(fnt(9.6))
        bw = QFontMetrics(fnt(9.6, QFont.DemiBold)).horizontalAdvance(s.btn) + 8
        p.drawText(QRectF(32, 0, r.width() - 40 - bw, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(p.font()).elidedText(s.text, Qt.ElideRight, int(r.width() - 44 - bw)))
        p.setPen(col)
        p.setFont(fnt(9.6, QFont.DemiBold))
        p.drawText(QRectF(r.width() - bw - 10, 0, bw, r.height()), Qt.AlignVCenter | Qt.AlignRight, s.btn)
