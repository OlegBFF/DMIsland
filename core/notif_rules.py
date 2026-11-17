"""Приоритеты и политика показа уведомлений. Без Qt и Windows — целиком тестируется."""
from datetime import datetime, time as dtime

IMPORTANT, SYSTEM, NORMAL = 'important', 'system', 'normal'
PRIORITY_NAMES = {IMPORTANT: 'Важное', SYSTEM: 'Система', NORMAL: 'Обычное'}

# Подстроки в нижнем регистре; сравниваются с «имя приложения + AUMID»
DEFAULT_IMPORTANT_APPS = (
    'telegram', 'whatsapp', 'signal', 'viber', 'discord', 'slack', 'teams', 'skype', 'messenger', 'zoom',
    'phone link', 'yourphone', 'связь с телефоном', 'сообщения', 'messages', 'max', 'вконтакте',
)
DEFAULT_IMPORTANT_WORDS = (
    'срочно', 'urgent', 'asap', 'звонок', 'пропущенный', 'missed call', 'incoming call', 'вызов',
    'код подтверждения', 'verification code', 'security code', 'одноразовый', 'one-time',
)
SYSTEM_MARKERS = (
    'windows.systemtoast', 'microsoft.windows.', 'windowsdefender', 'securityhealth', 'windowsupdate',
    'immersivecontrolpanel', 'batterysaver', 'windows.defender', 'microsoft.windows.shell',
    'безопасность windows', 'windows security', 'центр обновления', 'windows update', 'параметры', 'аккумулятор',
    'battery', 'bluetooth', 'устройства', 'диспетчер', 'storage sense', 'контроль памяти',
)


def split_list(text) -> list:
    return [x.strip().lower() for x in str(text or '').replace(';', ',').split(',') if x.strip()]


def _hay(app, app_id):
    return f"{app} {app_id}".lower()


def is_muted(app, app_id, muted_apps) -> bool:
    h = _hay(app, app_id)
    return any(m in h for m in split_list(muted_apps))


def classify(app, app_id, title, body, important_apps='', keywords='', source='windows') -> str:
    """important — сообщения и звонки, системное — события Windows и самого острова, всё остальное — обычное."""
    if source == 'island':
        return SYSTEM
    h = _hay(app, app_id)
    text = f"{title} {body}".lower()
    if any(a in h for a in split_list(important_apps)):
        return IMPORTANT
    if any(w in text for w in split_list(keywords)):
        return IMPORTANT
    if any(m in h for m in SYSTEM_MARKERS):
        return SYSTEM
    if any(a in h for a in DEFAULT_IMPORTANT_APPS):
        return IMPORTANT
    if any(w in text for w in DEFAULT_IMPORTANT_WORDS):
        return IMPORTANT
    return NORMAL


def _parse_hm(v):
    try:
        h, m = str(v).split(':')
        return dtime(int(h), int(m))
    except (ValueError, AttributeError):
        return None


def in_quiet_hours(now: datetime, start, end) -> bool:
    a, b = _parse_hm(start), _parse_hm(end)
    if a is None or b is None or a == b:
        return False
    t = now.time()
    return (a <= t < b) if a < b else (t >= a or t < b)         # интервал может переходить через полночь


def policy(priority, cfg, now: datetime, fullscreen=False, recording=False) -> dict:
    """Как показать: {'show': 'card'|'toast'|'silent', 'secs': float, 'sticky': bool, 'reason': str}.
    «Тихо» — уведомление только попадает в историю и счётчик; в полноэкранном режиме оно ждёт и появится сводкой."""
    if not cfg.get('notif_enabled', True):
        return {'show': 'silent', 'secs': 0, 'sticky': False, 'reason': 'off'}
    quiet = bool(cfg.get('notif_dnd')) or in_quiet_hours(now, cfg.get('notif_quiet_from'), cfg.get('notif_quiet_to'))
    if quiet and not (priority == IMPORTANT and cfg.get('notif_dnd_important', True)):
        return {'show': 'silent', 'secs': 0, 'sticky': False, 'reason': 'dnd'}
    if fullscreen:
        return {'show': 'silent', 'secs': 0, 'sticky': False, 'reason': 'fullscreen'}
    if priority == IMPORTANT:
        return {'show': 'card', 'secs': float(cfg.get('notif_important_secs', 15)), 'sticky': False, 'reason': ''}
    mode = cfg.get('notif_system' if priority == SYSTEM else 'notif_normal', 'toast')
    if mode == 'silent':
        return {'show': 'silent', 'secs': 0, 'sticky': False, 'reason': 'setting'}
    if recording and priority == NORMAL:
        return {'show': 'silent', 'secs': 0, 'sticky': False, 'reason': 'recording'}
    return {'show': mode, 'secs': 6.0 if mode == 'card' else 3.6, 'sticky': False, 'reason': ''}


def resolve_ui_scale(mode, logical_width) -> float:
    """Масштаб интерфейса: 'auto' подбирается по логической ширине основного монитора, иначе число."""
    try:
        if str(mode) != 'auto':
            return max(0.7, min(2.0, float(mode)))
    except ValueError:
        return 1.0
    if not logical_width:
        return 1.0
    if logical_width < 1400:
        return 0.9
    if logical_width < 2300:
        return 1.0
    if logical_width < 3000:
        return 1.2
    return 1.4


_WD = ('пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс')
_MON = ('янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек')


def format_time(ts: float, now: float) -> str:
    """Время уведомления: «сейчас», «5 мин назад», «сегодня 14:32», «вчера 21:05», «пн 09:10», «12 ноя»."""
    d = now - ts
    if d < 45:
        return 'сейчас'
    if d < 3600:
        return f"{int(d // 60) or 1} мин назад"
    t, n = datetime.fromtimestamp(ts), datetime.fromtimestamp(now)
    days = (n.date() - t.date()).days
    if days == 0:
        return t.strftime('сегодня %H:%M')
    if days == 1:
        return t.strftime('вчера %H:%M')
    if 1 < days < 7:
        return f"{_WD[t.weekday()]} {t:%H:%M}"
    return f"{t.day} {_MON[t.month - 1]}"


def snooze_options(now: datetime):
    """Варианты «Отложить»: [(подпись, момент возврата)]. «Вечером» — только пока не наступил вечер."""
    from datetime import timedelta
    opts = [('Через 5 минут', now + timedelta(minutes=5)), ('Через 15 минут', now + timedelta(minutes=15)),
            ('Через час', now + timedelta(hours=1)), ('Через 3 часа', now + timedelta(hours=3))]
    evening = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if evening - now > timedelta(hours=3, minutes=5):
        opts.append(('Сегодня вечером (18:00)', evening))
    tomorrow = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    opts.append(('Завтра утром (9:00)', tomorrow))
    return opts
