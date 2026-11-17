"""Панель «text»."""
import base64
import re
import urllib.parse
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QTextEdit, QWidget


class TextPanel:
    """Часть класса Island: TextPanel."""

    def pg_text(s):
        w, h = QWidget(), QHBoxLayout()
        w.setLayout(h)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(8)
        s.txt_ed = QTextEdit()
        s.txt_ed.setAcceptRichText(False)
        s.txt_ed.setPlaceholderText('Вставьте текст для конвертации раскладки, регистра, JSON, Base64, URL или ИИ…')
        h.addWidget(s.txt_ed, 3)

        grid = QGridLayout()
        grid.setSpacing(5)
        acts = [
            ('Раскладка RU↔EN', s.tx_layout), ('ВЕРХНИЙ', lambda: s.tx_mod(str.upper)),
            ('нижний', lambda: s.tx_mod(str.lower)), ('Заглавные', lambda: s.tx_mod(str.title)),
            ('Транслит', s.tx_translit), ('Лишние пробелы', lambda: s.tx_mod(lambda t: re.sub(r'\s+', ' ', t).strip())),
            ('JSON красиво', s.tx_json_pretty), ('JSON в строку', s.tx_json_min),
            ('→ Base64', lambda: s.tx_mod(lambda t: base64.b64encode(t.encode()).decode())),
            ('Base64 →', s.tx_b64_dec),
            ('→ URL', lambda: s.tx_mod(urllib.parse.quote)),
            ('URL →', lambda: s.tx_mod(urllib.parse.unquote)),
            ('Исправить (ИИ)', lambda: s.tx_ai('Исправь ошибки и пунктуацию без лишних комментариев:')),
            ('Перевести (ИИ)', lambda: s.tx_ai('Переведи на русский (или английский, если текст на русском):')),
            ('Кратко (ИИ)', lambda: s.tx_ai('Сократи суть текста в 2-3 пункта:')),
            ('В буфер', lambda: (QGuiApplication.clipboard().setText(s.txt_ed.toPlainText()), s.pop('Скопировано', 'Текст в буфере', (QColor('#34c759'), 'clip')))),
        ]
        for idx, (lbl, fn) in enumerate(acts):
            b = s.btn(lbl, fn)
            b.setStyleSheet('font-size:11.5px;padding:6px')
            grid.addWidget(b, idx // 2, idx % 2)
        h.addLayout(grid, 2)
        return w
