"""Панель «Чат»: шапка, лента сообщений с Markdown, поле ввода с вложениями и голосом, подсказки, всплывающие сообщения."""
import time
from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QVBoxLayout, QWidget
from ui.chat_widgets import ChatHeader, ChatView, Composer, NoticeBar, fg_col, line_col, surface
from ui.icons import VectorIcon
from ui.themes import STYLE
from ui.widgets import fnt


class ChatToast(QWidget):
    """Всплывающее сообщение внутри чата: остров в чате не сворачивается, поэтому тосты показываем здесь."""

    def __init__(s, parent):
        super().__init__(parent)
        s.title, s.sub, s.col, s.icon = '', '', QColor('#34c759'), 'check'
        s.t_end = 0.0
        s.setAttribute(Qt.WA_TransparentForMouseEvents)
        s.timer = QTimer(s)
        s.timer.setSingleShot(True)
        s.timer.timeout.connect(s.hide)
        s.hide()

    def show_toast(s, title, sub='', col=None, icon='check', secs=3.0):
        s.title, s.sub, s.icon = title, sub, icon
        s.col = QColor(col) if col is not None else QColor(STYLE['acc'])
        fm_t, fm_s = QFontMetrics(fnt(10.4, QFont.DemiBold)), QFontMetrics(fnt(9.2))
        w = min(max(fm_t.horizontalAdvance(title), fm_s.horizontalAdvance(sub)) + 66, max(s.parent().width() - 24, 200))
        s.setFixedSize(int(w), 48 if sub else 38)
        s.move(int((s.parent().width() - w) / 2), 46)
        s.raise_()
        s.show()
        s.timer.start(int(secs * 1000))
        s.update()

    def paintEvent(s, e):
        p = QPainter(s)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(s.rect()).adjusted(.5, .5, -.5, -.5)
        base = QColor('#f4f4f9') if STYLE['light'] else QColor('#1c1c22')
        p.setPen(QPen(QColor(s.col.red(), s.col.green(), s.col.blue(), 120), 1.2))
        p.setBrush(base)
        p.drawRoundedRect(r, r.height() / 2 if not s.sub else 18, r.height() / 2 if not s.sub else 18)
        VectorIcon.draw(p, s.icon, QRectF(10, r.height() / 2 - 12, 24, 24), QColor('white'), s.col)
        p.setPen(fg_col())
        p.setFont(fnt(10.4, QFont.DemiBold))
        tw = r.width() - 52
        if s.sub:
            p.drawText(QRectF(44, 5, tw, 20), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(s.title, Qt.ElideRight, int(tw)))
            p.setPen(fg_col(150))
            p.setFont(fnt(9.2))
            p.drawText(QRectF(44, 24, tw, 18), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(s.sub, Qt.ElideRight, int(tw)))
        else:
            p.drawText(QRectF(44, 0, tw, r.height()), Qt.AlignVCenter | Qt.AlignLeft, QFontMetrics(p.font()).elidedText(s.title, Qt.ElideRight, int(tw)))


class ChatPanel:
    """Часть класса Island: ChatPanel."""

    def pg_chat(s):
        w, v = QWidget(), QVBoxLayout()
        w.setLayout(v)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        s.chat_head = ChatHeader()
        s.chat_notice = NoticeBar()
        s.chat_view = ChatView()
        s.composer = Composer()
        v.addWidget(s.chat_head)
        v.addWidget(s.chat_notice)
        v.addWidget(s.chat_view, 1)
        v.addWidget(s.composer)
        s.chat_toast_w = ChatToast(w)

        s.chat_head.newClicked.connect(s.new_chat)
        s.chat_head.historyClicked.connect(s.chat_history_menu)
        s.chat_head.closeClicked.connect(s.close_island)
        s.chat_notice.clicked.connect(s.open_settings)
        s.chat_view.suggestion.connect(s.chat_suggest)
        s.chat_view.linkClicked.connect(s.chat_link)
        s.chat_view.imageClicked.connect(s.chat_open_image)
        s.chat_view.copyRequested.connect(s.chat_copy)
        s.composer.submitted.connect(s.submit_chat)
        s.composer.stopClicked.connect(s.stop_chat)
        s.composer.micClicked.connect(lambda: s.chat_voice(False))
        s.composer.attachClicked.connect(s.chat_attach_menu)
        s.composer.attachRemoved.connect(s.att_remove)
        s.composer.escaped.connect(s.close_island)
        s.render_chat()
        return w

    def chat_toast(s, title, sub='', col=None, secs=3.0, icon='check'):
        if hasattr(s, 'chat_toast_w'):
            s.chat_toast_w.show_toast(title, sub, col, icon, secs)
