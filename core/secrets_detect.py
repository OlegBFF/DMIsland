"""Распознавание секретных данных в тексте (ключи, токены, пароли, номера карт) — без Qt и Windows."""
import math
import re


_PATTERNS = [
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'), 'Приватный ключ'),
    (re.compile(r'^eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$'), 'JWT-токен'),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), 'Ключ AWS'),
    (re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b'), 'Токен GitHub'),
    (re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'), 'API-ключ'),
    (re.compile(r'\b[sr]k_live_[A-Za-z0-9]{16,}\b'), 'Ключ Stripe'),
    (re.compile(r'\bxox[baprs]-[A-Za-z0-9-]{10,}\b'), 'Токен Slack'),
    (re.compile(r'\bAIza[0-9A-Za-z_-]{35}\b'), 'Ключ Google'),
    (re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}'), 'Токен доступа'),
    (re.compile(r'(?i)\b(?:pass(?:word)?|passwd|pwd|пароль|secret|token|api[_-]?key)\s*[:=]\s*\S{4,}'), 'Пароль'),
]

_IBAN = re.compile(r'^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$')


def luhn_ok(digits: str) -> bool:
    if not 13 <= len(digits) <= 19 or not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_ok(text: str) -> bool:
    t = text.replace(' ', '').upper()
    if not _IBAN.match(t):
        return False
    moved = t[4:] + t[:4]
    num = ''.join(str(int(c, 36)) for c in moved)
    return int(num) % 97 == 1


def entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))


def _looks_like_password(t: str) -> bool:
    """Одно «слово» без пробелов, смесь регистров/цифр/символов — похоже на пароль, а не на обычный текст."""
    if not 8 <= len(t) <= 64 or re.search(r'\s', t):
        return False
    if re.match(r'^(?:[a-z][a-z0-9+.-]*://|www\.)', t, re.I) or '@' in t[1:-1] and '.' in t.split('@')[-1]:
        return False                                   # ссылка или e-mail
    if re.match(r'^(?:[A-Za-z]:)?[\\/]', t) or t.count('/') > 1 or t.count('\\') > 1:
        return False                                   # путь к файлу
    classes = sum(bool(re.search(p, t)) for p in (r'[a-z]', r'[A-Z]', r'\d', r'[^A-Za-z0-9]'))
    if classes < 3:
        return False
    return entropy(t) >= 3.0


def classify(text: str, heuristic: bool = True):
    """Возвращает название типа секрета (например «API-ключ») или None, если текст обычный."""
    t = text.strip()
    if not t:
        return None
    for rx, label in _PATTERNS:
        if rx.search(t):
            return label
    if len(t) <= 200:
        digits = re.sub(r'[ -]', '', t)
        if re.fullmatch(r'[\d -]{13,23}', t) and luhn_ok(digits):
            return 'Банковская карта'
        if iban_ok(t):
            return 'IBAN'
        if heuristic and '\n' not in t and _looks_like_password(t):
            return 'Возможный пароль'
    return None
