"""«Настроение» острова: какой цвет он принимает прямо сейчас. Без Qt — цвета это (r, g, b).

Приоритет (сверху вниз): цвет текущего события (Bluetooth — голубой…) → важное уведомление → запись экрана (красный) →
таймер (мягкий оранжевый) → музыка (цвета обложки) → ничего (цвет темы).
"""
RED, ORANGE, BLUE, GREEN, YELLOW = (255, 69, 58), (255, 159, 10), (64, 156, 255), (52, 199, 89), (255, 214, 10)

EVENT_COLORS = (                       # слова в заголовке тоста → цвет события
    (('bluetooth', 'науш', 'airpods', 'buds'), (90, 190, 255)),
    (('wi-fi', 'wifi', 'сеть', 'интернет'), (100, 210, 255)),
    (('таймер', 'напомин', 'время вышло'), ORANGE),
    (('запись', 'скриншот'), RED),
    (('батаре', 'заряд', 'питани'), GREEN),
    (('яркост',), YELLOW),
)


def event_color(title: str, ok: bool = True):
    """Цвет тоста по его заголовку; при ошибке (ok=False) всегда красный. None — событие без своего цвета."""
    if not ok:
        return RED
    t = (title or '').casefold()
    for words, col in EVENT_COLORS:
        if any(w in t for w in words):
            return col
    return None


def pick_mood(st: dict):
    """st: toast_col, card_prio, unread_important, recording, timer, playing, cover.
    Возвращает (имя, (r, g, b) или None, сила 0..1)."""
    if st.get('toast_col'):
        return 'event', tuple(st['toast_col']), 0.85
    prio = st.get('card_prio')
    if prio == 'important':
        return 'important', RED, 1.0
    if prio == 'system':
        return 'system', BLUE, 0.7
    if st.get('recording'):
        return 'recording', RED, 0.9
    if st.get('unread_important'):
        return 'important', RED, 0.55
    if st.get('timer'):
        return 'timer', ORANGE, 0.5
    if st.get('playing') and st.get('cover'):
        return 'music', tuple(st['cover']), 0.7
    return 'none', None, 0.0


def lerp_color(cur, tgt, dt: float, rate: float = 6.0):
    """Плавное приближение цвета к цели (экспоненциальное, не зависит от частоты кадров)."""
    import math
    k = 1.0 - math.exp(-max(dt, 0.0) * rate)
    return tuple(c + (t - c) * k for c, t in zip(cur, tgt))
