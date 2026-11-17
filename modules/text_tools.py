"""Текстовые инструменты: раскладка, транслит, JSON, Base64."""
import base64
import json
from PySide6.QtGui import QColor


class TextToolsMixin:
    """Часть класса Island: TextToolsMixin."""

    # ==================== ТЕКСТ И ЗАЩИЩЁННЫЙ ИИ ====================
    def tx_mod(s, fn):
        try:
            s.txt_ed.setPlainText(fn(s.txt_ed.toPlainText()))
        except Exception:
            pass

    def tx_layout(s):
        en = "qwertyuiop[]asdfghjkl;'zxcvbnm,./`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>?~"
        ru = "йцукенгшщзхъфывапролджэячсмитьбю.ёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,Ё"
        t = s.txt_ed.toPlainText()
        ru_cnt = sum(1 for c in t if c in ru)
        table = str.maketrans(ru, en) if ru_cnt > len(t) / 3 else str.maketrans(en, ru)
        s.txt_ed.setPlainText(t.translate(table))

    def tx_translit(s):
        mp = {'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh','з':'z','и':'i','й':'y',
              'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
              'х':'kh','ц':'ts','ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya'}
        res = [mp.get(c.lower(), c).capitalize() if c.isupper() else mp.get(c.lower(), c) for c in s.txt_ed.toPlainText()]
        s.txt_ed.setPlainText(''.join(res))

    def tx_json_pretty(s):
        try:
            s.txt_ed.setPlainText(json.dumps(json.loads(s.txt_ed.toPlainText()), ensure_ascii=False, indent=2))
        except Exception:
            s.pop('Ошибка JSON', 'Некорректный формат JSON', (QColor('#ff453a'), 'text'))

    def tx_json_min(s):
        try:
            s.txt_ed.setPlainText(json.dumps(json.loads(s.txt_ed.toPlainText()), ensure_ascii=False, separators=(',', ':')))
        except Exception:
            pass

    def tx_b64_dec(s):
        try:
            s.txt_ed.setPlainText(base64.b64decode(s.txt_ed.toPlainText().encode()).decode('utf-8', 'ignore'))
        except Exception:
            pass
