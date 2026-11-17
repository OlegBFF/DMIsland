"""Заметки."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from core.config import save_cfg


class NotesMixin:
    """Часть класса Island: NotesMixin."""

    # ==================== ЗАМЕТКИ И ТАЙМЕР ====================
    def switch_note(s, idx):
        s.save_current_note()
        s.note_idx = idx
        s.note.blockSignals(True)
        s.note.setHtml(s.cfg['notes'][idx].get('html', ''))
        s.note.blockSignals(False)

    def save_current_note(s):
        if 0 <= s.note_idx < len(s.cfg['notes']):
            s.cfg['notes'][s.note_idx]['html'] = s.note.toHtml()
            save_cfg(s.cfg)

    def fmt_note(s, mode):
        cur = s.note.textCursor()
        fmt = QTextCharFormat()
        if mode == 'b':
            fmt.setFontWeight(QFont.Bold if cur.charFormat().fontWeight() != QFont.Bold else QFont.Normal)
        elif mode == 'i':
            fmt.setFontItalic(not cur.charFormat().fontItalic())
        elif mode == 's':
            fmt.setFontStrikeOut(not cur.charFormat().fontStrikeOut())
        elif mode == 'hl':
            fmt.setBackground(QColor('#ff9f0a') if cur.charFormat().background().color() != QColor('#ff9f0a') else Qt.transparent)
        cur.mergeCharFormat(fmt)
