"""Что можно сделать с уведомлением: ссылки, коды, картинки, управление музыкой, группировка по приложениям. Без Qt и Windows.

Windows отдаёт стороннему приложению только заголовок и текст чужого уведомления: кнопок и вложений тоста
UserNotificationListener не показывает. Поэтому «действия» здесь строятся из самого текста сообщения:
ссылка → «Открыть ссылку», код подтверждения → «Копировать код», адрес картинки или путь к файлу → превью.
"""
import re
from urllib.parse import urlparse

_URL = re.compile(r'(?i)\b(?:https?://|www\.)[^\s<>"\'«»)\]]+')
_IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
_WIN_PATH = re.compile(r'(?i)\b[a-z]:\\[^\r\n<>"|?*]+?\.(?:png|jpe?g|gif|webp|bmp)\b')
_CODE = re.compile(r'(?i)(?:код|code|пароль|password|otp|пин|pin)\D{0,40}?(\d{4,8})\b|\b(\d{4,8})\b\D{0,20}?(?:—|-|is|это)?\s*(?:ваш\s+)?(?:код|code)')
_PHONE = re.compile(r'(?<![\w.])(\+?\d[\d\s().-]{8,16}\d)(?![\w.])')

MUSIC_APPS = ('spotify', 'yandex music', 'яндекс музык', 'яндекс.музык', 'vlc', 'itunes', 'apple music', 'deezer', 'tidal',
              'youtube music', 'soundcloud', 'звук', 'vk музык', 'вк музык', 'музык', 'music', 'foobar', 'aimp', 'winamp',
              'groove', 'amazon music', 'pandora', 'tunein', 'plexamp', 'mpc', 'potplayer', 'media player')


def find_urls(text: str, limit: int = 3):
    """Ссылки из текста: только http(s); www.* дополняется схемой. Без дубликатов, максимум limit."""
    out = []
    for m in _URL.finditer(text or ''):
        u = m.group(0).rstrip('.,;:!?')
        if u.lower().startswith('www.'):
            u = 'https://' + u
        p = urlparse(u)
        if p.scheme in ('http', 'https') and p.hostname and u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


def host_of(url: str) -> str:
    h = (urlparse(url).hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def find_image_refs(text: str, limit: int = 3):
    """Картинки в тексте: [('url', адрес)] для ссылок на изображения и [('file', путь)] для локальных файлов."""
    out = []
    for u in find_urls(text, 8):
        path = urlparse(u).path.lower()
        if path.endswith(_IMG_EXT):
            out.append(('url', u))
    for m in _WIN_PATH.finditer(text or ''):
        out.append(('file', m.group(0)))
    seen, res = set(), []
    for kind, ref in out:
        if ref not in seen:
            seen.add(ref)
            res.append((kind, ref))
    return res[:limit]


def find_code(text: str):
    """Код подтверждения (4–8 цифр рядом со словом «код»/«code»/«пароль») или None."""
    m = _CODE.search(text or '')
    return (m.group(1) or m.group(2)) if m else None


def find_phone(text: str):
    m = _PHONE.search(text or '')
    if not m:
        return None
    digits = re.sub(r'\D', '', m.group(1))
    return m.group(1).strip() if 10 <= len(digits) <= 15 else None


def is_music(n: dict) -> bool:
    h = f"{n.get('app') or ''} {n.get('app_id') or ''}".lower()
    return any(k in h for k in MUSIC_APPS)


def actions_for(n: dict, can_reply: bool = False, now_playing_app: str = ''):
    """Список действий карточки: [{'key', 'label', 'arg'?}] в порядке важности. Системные кнопки (Отложить, Прочитано) добавляет карточка."""
    text = f"{n.get('title') or ''}\n{n.get('body') or ''}"
    acts = []
    if can_reply:
        acts.append({'key': 'reply', 'label': 'Ответить'})
    code = find_code(text)
    if code:
        acts.append({'key': 'copy_code', 'label': f'Копировать {code}', 'arg': code})
    for u in find_urls(text, 2):
        acts.append({'key': 'link', 'label': host_of(u)[:22] or 'Ссылка', 'arg': u})
    ph = find_phone(text) if not code else None
    if ph:
        acts.append({'key': 'copy_phone', 'label': 'Копировать номер', 'arg': ph})
    music = is_music(n) or bool(now_playing_app and now_playing_app.lower() in f"{n.get('app') or ''} {n.get('app_id') or ''}".lower())
    if music:
        acts.append({'key': 'music', 'label': ''})
    return acts


# ==================== ГРУППИРОВКА ПО ПРИЛОЖЕНИЯМ ====================
def group_by_app(items):
    """[(ключ, название, [уведомления])] — группы идут в порядке самого свежего сообщения, внутри — от новых к старым."""
    groups, order = {}, []
    for n in items:
        key = (n.get('app_id') or n.get('app') or '?').casefold()
        if key not in groups:
            groups[key] = {'key': key, 'app': n.get('app') or n.get('app_id') or 'Уведомление', 'items': []}
            order.append(key)
        groups[key]['items'].append(n)
    return [(k, groups[k]['app'], groups[k]['items']) for k in order]


def group_summary(items) -> dict:
    """Сводка по группе: сколько всего, непрочитанных, самое важное."""
    unread = sum(1 for n in items if not n.get('read'))
    rank = {'important': 0, 'system': 1, 'normal': 2}
    top = min((n.get('priority', 'normal') for n in items), key=lambda p: rank.get(p, 3), default='normal')
    return {'total': len(items), 'unread': unread, 'priority': top}


def queue_groups(queue):
    """Очередь карточек → группы подряд идущих сообщений одного приложения: [(app_id, [индексы в очереди])]."""
    out = []
    for i, n in enumerate(queue):
        key = (n.get('app_id') or n.get('app') or '?').casefold()
        for g in out:
            if g[0] == key:
                g[1].append(i)
                break
        else:
            out.append((key, [i]))
    return out
