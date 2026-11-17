"""Расписания напоминаний: правила повторения и разбор фраз вроде «каждый понедельник в 10:00». Без Qt."""
import calendar
import re
from datetime import datetime, time as dtime, timedelta

WD_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

_ISO = '%Y-%m-%dT%H:%M:%S'


def _dt(v: str) -> datetime:
    return datetime.strptime(v[:19] if len(v) > 16 else v[:16] + ':00', _ISO)


def _hm(v: str):
    h, m = v.split(':')
    return dtime(int(h), int(m))


def once(at: datetime) -> dict:
    return {'type': 'once', 'at': at.replace(microsecond=0).strftime(_ISO)}


def daily(hm: str) -> dict:
    return {'type': 'daily', 'time': hm}


def weekly(hm: str, days) -> dict:
    return {'type': 'weekly', 'time': hm, 'days': sorted(set(int(d) for d in days))}


def monthly(hm: str, day: int) -> dict:
    return {'type': 'monthly', 'time': hm, 'day': int(day)}


def interval(minutes: int, anchor: datetime) -> dict:
    return {'type': 'interval', 'minutes': max(1, int(minutes)), 'anchor': anchor.replace(microsecond=0).strftime(_ISO)}


def next_occurrence(rule: dict, after: datetime):
    """Ближайшее срабатывание строго позже `after` или None (для одноразовых в прошлом)."""
    t = rule.get('type')
    if t == 'once':
        at = _dt(rule['at'])
        return at if at > after else None
    if t == 'interval':
        step = timedelta(minutes=max(1, int(rule['minutes'])))
        anchor = _dt(rule['anchor'])
        if after < anchor:
            return anchor
        n = int((after - anchor) / step) + 1
        return anchor + n * step
    tm = _hm(rule['time'])
    if t == 'daily':
        cand = datetime.combine(after.date(), tm)
        return cand if cand > after else cand + timedelta(days=1)
    if t == 'weekly':
        days = set(rule.get('days') or range(7))
        for add in range(8):
            d = after.date() + timedelta(days=add)
            if d.weekday() in days:
                cand = datetime.combine(d, tm)
                if cand > after:
                    return cand
        return None
    if t == 'monthly':
        y, m = after.year, after.month
        for _ in range(14):
            day = min(int(rule['day']), calendar.monthrange(y, m)[1])
            cand = datetime.combine(datetime(y, m, day).date(), tm)
            if cand > after:
                return cand
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def _day_word(dt: datetime, now: datetime) -> str:
    d = (dt.date() - now.date()).days
    if d == 0:
        return 'сегодня'
    if d == 1:
        return 'завтра'
    return dt.strftime('%d.%m' if dt.year == now.year else '%d.%m.%Y')


def format_due(dt, now: datetime) -> str:
    if dt is None:
        return '—'
    return f"{_day_word(dt, now)} {dt:%H:%M}"


def describe(rule: dict, now: datetime = None) -> str:
    now = now or datetime.now()
    t = rule.get('type')
    if t == 'once':
        at = _dt(rule['at'])
        return f"Один раз · {_day_word(at, now)} {at:%H:%M}"
    if t == 'daily':
        return f"Каждый день · {rule['time']}"
    if t == 'weekly':
        days = rule.get('days') or []
        if days == [0, 1, 2, 3, 4]:
            names = 'По будням'
        elif days == [5, 6]:
            names = 'По выходным'
        elif len(days) == 7:
            names = 'Каждый день'
        else:
            names = ', '.join(WD_SHORT[d] for d in days)
        return f"{names} · {rule['time']}"
    if t == 'monthly':
        return f"Каждое {rule['day']}-е число · {rule['time']}"
    if t == 'interval':
        m = int(rule['minutes'])
        return f"Каждые {m // 60} ч" + (f" {m % 60} мин" if m % 60 else '') if m >= 60 else f"Каждые {m} мин"
    return '—'


def validate(rule: dict):
    """Бросает ValueError, если правило некорректно."""
    t = rule.get('type')
    if t not in ('once', 'daily', 'weekly', 'monthly', 'interval'):
        raise ValueError('Неизвестный тип повторения')
    if t == 'once':
        _dt(rule['at'])
    elif t == 'interval':
        if int(rule['minutes']) < 1:
            raise ValueError('Интервал должен быть не меньше минуты')
        _dt(rule['anchor'])
    else:
        _hm(rule['time'])
        if t == 'weekly' and not rule.get('days'):
            raise ValueError('Выберите хотя бы один день недели')
        if t == 'monthly' and not 1 <= int(rule['day']) <= 31:
            raise ValueError('День месяца: от 1 до 31')


# ==================== РАЗБОР ТЕКСТА ====================
_WD = (r'(?:понедельник\w*|вторник\w*|сред\w*|четверг\w*|пятниц\w*|суббот\w*|воскресен\w*|пн|вт|ср|чт|пт|сб|вс)')
_RX_WD = re.compile(rf'(?:(каждый|каждую|каждое|по|в|во|на)\s+)({_WD})\b', re.I)
_RX_INTERVAL = re.compile(r'\bкажд(?:ые|ый|ую|ое)\s+(?:(\d+)\s*)?(мин\w*|час\w*|ч)\b|\bкаждые\s+полчаса\b', re.I)
_RX_AFTER = re.compile(r'\bчерез\s+(?:(\d+)\s*)?(полчаса|секунд\w*|сек|мин\w*|час\w*|ч|дн\w*|день|сутки)\b', re.I)
_RX_DAILY = re.compile(r'\b(?:ежедневно|каждый\s+день|каждые\s+сутки)\b', re.I)
_RX_WORKDAYS = re.compile(r'\b(?:по\s+будн\w+|в\s+будни|по\s+рабочим\s+дням|каждый\s+будний\s+день)\b', re.I)
_RX_WEEKEND = re.compile(r'\b(?:по\s+выходным|в\s+выходные)\b', re.I)
_RX_MONTHLY = re.compile(r'\bкажд(?:ое|ого)\s+(\d{1,2})(?:-?(?:е|го))?\s+(?:число|числа)\b|\b(\d{1,2})(?:-?(?:е|го))?\s+числа\s+кажд\w+\s+месяц\w*', re.I)
_RX_TIME = re.compile(r'(?<![\d.:])(\d{1,2}):(\d{2})(?![\d:])(?:\s*(утра|дня|вечера|ночи))?', re.I)
_RX_HOUR = re.compile(r'\bв\s+(\d{1,2})\s+(утра|дня|вечера|ночи)\b|\bв\s+(\d{1,2})\s*(?:ч|час|часов|часа)?(?![\d:.]|\s*(?:мин|сек))\b(?!\s*(?:числа|-))', re.I)
_RX_DATE = re.compile(r'(?<![\d:])(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?(?![\d:])')
_RX_ISO = re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b')
_RX_DAYWORD = re.compile(r'\b(послезавтра|завтра|сегодня)\b', re.I)
_RX_PREFIX = re.compile(r'^\s*(?:напомни(?:ть)?|напоминание)\s*(?:мне)?\s*[:,\-–—]?\s*', re.I)


def _wd_index(word: str) -> int:
    w = word.lower()
    for i, stem in enumerate(('пон', 'вт', 'сре', 'чет', 'пят', 'суб', 'вос')):
        if w.startswith(stem):
            return i
    return {'пн': 0, 'вт': 1, 'ср': 2, 'чт': 3, 'пт': 4, 'сб': 5, 'вс': 6}[w]


def _apply_ampm(h: int, word):
    w = (word or '').lower()
    if w in ('дня', 'вечера') and h < 12:
        return h + 12
    if w == 'ночи' and h == 12:
        return 0
    return h


def parse_reminder(raw: str, now: datetime = None):
    """Разбирает фразу и возвращает (текст, правило). Бросает ValueError с понятным сообщением по-русски."""
    now = (now or datetime.now()).replace(microsecond=0)
    text = _RX_PREFIX.sub('', raw)
    spans = []

    def grab(rx, s):
        m = rx.search(s)
        if m:
            spans.append(m.group(0))
        return m

    rule = None
    # --- интервалы и «через …» ---
    m = grab(_RX_INTERVAL, text)
    if m:
        unit = (m.group(2) or 'мин').lower()
        n = int(m.group(1) or 1)
        mins = 30 if 'полчаса' in m.group(0).lower() else (n * 60 if unit.startswith('ч') else n)
        return _clean(text, spans), interval(mins, now)
    m = grab(_RX_AFTER, text)
    if m:
        unit, n = m.group(2).lower(), int(m.group(1) or 1)
        if unit == 'полчаса':
            delta = timedelta(minutes=30)
        elif unit.startswith('сек'):
            delta = timedelta(seconds=n)
        elif unit.startswith('мин'):
            delta = timedelta(minutes=n)
        elif unit.startswith('ч'):
            delta = timedelta(hours=n)
        else:
            delta = timedelta(days=n)
        return _clean(text, spans), once(now + delta)

    # --- время суток ---
    hm = None
    m = grab(_RX_TIME, text)
    if m:
        h, mi = _apply_ampm(int(m.group(1)), m.group(3)), int(m.group(2))
        if h > 23 or mi > 59:
            raise ValueError('Некорректное время')
        hm = (h, mi)
    else:
        m = grab(_RX_HOUR, text)
        if m:
            h = _apply_ampm(int(m.group(1) or m.group(3)), m.group(2))
            if h > 23:
                raise ValueError('Некорректное время')
            hm = (h, 0)
    tstr = f"{hm[0]:02d}:{hm[1]:02d}" if hm else None

    # --- повторяющиеся ---
    if grab(_RX_DAILY, text):
        rule = ('daily', None)
    elif grab(_RX_WORKDAYS, text):
        rule = ('weekly', [0, 1, 2, 3, 4])
    elif grab(_RX_WEEKEND, text):
        rule = ('weekly', [5, 6])
    else:
        m = grab(_RX_MONTHLY, text)
        if m:
            rule = ('monthly', int(m.group(1) or m.group(2)))
        else:
            m = _RX_WD.search(text)
            if m and m.group(1).lower() in ('каждый', 'каждую', 'каждое', 'по'):
                spans.append(m.group(0))
                rule = ('weekly', [_wd_index(m.group(2))])
    if rule:
        if not tstr:
            raise ValueError('Для повторяющегося напоминания укажите время, например «в 9:00»')
        kind, arg = rule
        if kind == 'daily':
            return _clean(text, spans), daily(tstr)
        if kind == 'weekly':
            return _clean(text, spans), weekly(tstr, arg)
        return _clean(text, spans), monthly(tstr, arg)

    # --- одноразовые: дата / день недели / «завтра» ---
    day = None
    m = grab(_RX_ISO, text)
    if m:
        day = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    else:
        m = grab(_RX_DATE, text)
        if m:
            d, mo = int(m.group(1)), int(m.group(2))
            y = int(m.group(3)) if m.group(3) else now.year
            y += 2000 if y < 100 else 0
            try:
                day = datetime(y, mo, d).date()
            except ValueError:
                raise ValueError('Некорректная дата')
            if not m.group(3) and day < now.date():          # «20.01» в ноябре — это январь следующего года
                day = datetime(y + 1, mo, d).date()
        else:
            m = grab(_RX_DAYWORD, text)
            if m:
                day = now.date() + timedelta(days={'сегодня': 0, 'завтра': 1, 'послезавтра': 2}[m.group(1).lower()])
            else:
                m = _RX_WD.search(text)
                if m:
                    spans.append(m.group(0))
                    wd = _wd_index(m.group(2))
                    day = now.date() + timedelta(days=(wd - now.weekday()) % 7)
                    if tstr and day == now.date() and datetime.combine(day, datetime.min.time().replace(hour=hm[0], minute=hm[1])) <= now:
                        day += timedelta(days=7)
    if not tstr:
        raise ValueError('Укажите время: «в 16:30», «через 15 мин», «завтра в 9:00»')
    if day is None:
        day = now.date()
        if datetime.combine(day, datetime.min.time().replace(hour=hm[0], minute=hm[1])) <= now:
            day += timedelta(days=1)
    at = datetime.combine(day, datetime.min.time().replace(hour=hm[0], minute=hm[1]))
    if at <= now:
        raise ValueError('Это время уже прошло')
    return _clean(text, spans), once(at)


def _clean(text: str, spans) -> str:
    for sp in spans:
        text = text.replace(sp, ' ', 1)
    text = re.sub(r'\s+', ' ', text).strip(' ,.-–—:;')
    text = re.sub(r'^(?:в|на|к|и)\s+(?=\S)', '', text, flags=re.I) if len(text.split()) > 1 else text
    text = re.sub(r'\s+(?:в|на|к)$', '', text, flags=re.I).strip(' ,.-–—:;')
    return text or 'Напоминание'
