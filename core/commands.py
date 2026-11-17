"""Разбор команд ассистента (набранных или сказанных голосом). Без Qt и Windows — целиком тестируется.

Команды разбираются ПРАВИЛАМИ, а не моделью: ответ ИИ или текст с экрана / из буфера никогда не запускают действия
на компьютере (иначе чужой текст с подсказкой вроде «открой такой-то сайт» мог бы ими управлять).
Если фраза не похожа на команду, parse() вернёт None и она уйдёт в чат как обычный вопрос.
"""
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlparse

# индексы вкладок острова (порядок задан в ui/island.py: build)
TABS = {'home': 0, 'clip': 1, 'shelf': 2, 'text': 3, 'chat': 4, 'notes': 5, 'weather': 6, 'sys': 7, 'notifs': 8}
_TAB_WORDS = (
    ('главн', 'home'), ('домой', 'home'), ('буфер', 'clip'), ('полк', 'shelf'), ('текст', 'text'),
    ('чат', 'chat'), ('диалог', 'chat'), ('заметк', 'notes'), ('напоминан', 'notes'), ('погод', 'weather'),
    ('управлен', 'sys'), ('уведомлен', 'notifs'),
)
TAB_TITLES = {'home': 'Главная', 'clip': 'Буфер', 'shelf': 'Полка', 'text': 'Текст', 'chat': 'Чат',
              'notes': 'Заметки', 'weather': 'Погода', 'sys': 'Управление', 'notifs': 'Уведомления'}

SITES = {   # нормализованные имена → (название, адрес)
    ('youtube', 'ютуб', 'ютьюб', 'you tube', 'ютюб'): ('YouTube', 'https://www.youtube.com'),
    ('google', 'гугл'): ('Google', 'https://www.google.com'),
    ('github', 'гитхаб', 'гит хаб'): ('GitHub', 'https://github.com'),
    ('gmail', 'гмейл', 'джимейл'): ('Gmail', 'https://mail.google.com'),
    ('яндекс', 'yandex'): ('Яндекс', 'https://yandex.ru'),
    ('яндекс музыка', 'яндекс музыку', 'yandex music'): ('Яндекс Музыка', 'https://music.yandex.ru'),
    ('вк', 'vk', 'вконтакте', 'в контакте'): ('ВКонтакте', 'https://vk.com'),
    ('chatgpt', 'чат gpt', 'чатгпт', 'чат гпт'): ('ChatGPT', 'https://chatgpt.com'),
    ('claude', 'клод'): ('Claude', 'https://claude.ai'),
    ('википедия', 'википедию', 'wikipedia'): ('Википедия', 'https://ru.wikipedia.org'),
    ('reddit', 'реддит'): ('Reddit', 'https://www.reddit.com'),
    ('twitch', 'твич'): ('Twitch', 'https://www.twitch.tv'),
    ('netflix', 'нетфликс'): ('Netflix', 'https://www.netflix.com'),
    ('кинопоиск', 'kinopoisk'): ('Кинопоиск', 'https://www.kinopoisk.ru'),
    ('ozon', 'озон'): ('Ozon', 'https://www.ozon.ru'),
    ('wildberries', 'вайлдберриз', 'вайлдберрис'): ('Wildberries', 'https://www.wildberries.ru'),
    ('avito', 'авито'): ('Авито', 'https://www.avito.ru'),
    ('2гис', '2gis', 'два гис'): ('2ГИС', 'https://2gis.ru'),
    ('карты', 'google maps', 'гугл карты'): ('Карты', 'https://www.google.com/maps'),
    ('переводчик', 'google translate'): ('Переводчик', 'https://translate.google.com'),
    ('hh', 'хх', 'hh.ru', 'хэдхантер'): ('hh.ru', 'https://hh.ru'),
}

# встроенные программы Windows (имя → что запускать); остальное ищется в лаунчере острова и в меню «Пуск»
BUILTIN_APPS = {
    ('блокнот', 'notepad'): ('Блокнот', 'notepad.exe'),
    ('калькулятор', 'calculator', 'calc'): ('Калькулятор', 'calc.exe'),
    ('проводник', 'explorer', 'мой компьютер', 'этот компьютер'): ('Проводник', 'explorer.exe'),
    ('диспетчер задач', 'task manager'): ('Диспетчер задач', 'taskmgr.exe'),
    ('paint', 'пэйнт', 'пейнт'): ('Paint', 'mspaint.exe'),
    ('командная строка', 'cmd', 'консоль'): ('Командная строка', 'cmd.exe'),
    ('powershell', 'пауэршелл', 'павершелл'): ('PowerShell', 'powershell.exe'),
    ('терминал', 'windows terminal'): ('Терминал', 'wt.exe'),
    ('ножницы', 'snipping tool'): ('Ножницы', 'snippingtool.exe'),
    ('параметры', 'настройки', 'настройки windows'): ('Параметры', 'ms-settings:'),
    ('панель управления', 'control panel'): ('Панель управления', 'control.exe'),
    ('bluetooth', 'блютуз'): ('Bluetooth', 'ms-settings:bluetooth'),
    ('wifi', 'wi-fi', 'вайфай', 'вай фай'): ('Wi-Fi', 'ms-settings:network-wifi'),
}


@dataclass
class Cmd:
    action: str
    args: dict = field(default_factory=dict)
    label: str = ''


# ==================== ЧИСЛА ПРОПИСЬЮ ====================
_NUM = {'ноль': 0, 'один': 1, 'одну': 1, 'одна': 1, 'два': 2, 'две': 2, 'три': 3, 'четыре': 4, 'пять': 5, 'шесть': 6,
        'семь': 7, 'восемь': 8, 'девять': 9, 'десять': 10, 'одиннадцать': 11, 'двенадцать': 12, 'тринадцать': 13,
        'четырнадцать': 14, 'пятнадцать': 15, 'шестнадцать': 16, 'семнадцать': 17, 'восемнадцать': 18,
        'девятнадцать': 19, 'двадцать': 20, 'тридцать': 30, 'сорок': 40, 'пятьдесят': 50, 'шестьдесят': 60,
        'семьдесят': 70, 'восемьдесят': 80, 'девяносто': 90, 'сто': 100, 'двести': 200, 'триста': 300,
        'четыреста': 400, 'пятьсот': 500,
        # родительный падеж: «до двадцати пяти»
        'двух': 2, 'трех': 3, 'четырех': 4, 'пяти': 5, 'шести': 6, 'семи': 7, 'восьми': 8, 'девяти': 9, 'десяти': 10,
        'пятнадцати': 15, 'двадцати': 20, 'тридцати': 30, 'сорока': 40, 'пятидесяти': 50, 'шестидесяти': 60,
        'семидесяти': 70, 'восьмидесяти': 80, 'девяноста': 90, 'ста': 100}


def _rank(v: int) -> int:
    return 3 if v >= 100 else (2 if v >= 20 else (1.5 if v >= 10 else 1))


def words_to_digits(text: str) -> str:
    """«поставь громкость тридцать пять процентов» → «поставь громкость 35 процентов»."""
    out, acc, last = [], None, 99
    for tok in text.split(' '):
        v = _NUM.get(tok)
        if v is None:
            if acc is not None:
                out.append(str(acc))
                acc, last = None, 99
            out.append(tok)
            continue
        r = _rank(v)
        if acc is not None and (r >= last or last == 1.5):      # «пять пять», «одиннадцать два» — это два числа
            out.append(str(acc))
            acc, last = None, 99
        acc = (acc or 0) + v
        last = r
    if acc is not None:
        out.append(str(acc))
    return ' '.join(out)


# ==================== НОРМАЛИЗАЦИЯ ====================
_FILLER = re.compile(r'^(?:(?:эй|слушай|ну|а|так|давай|остров|island|ассистент|пожалуйста|плиз|можешь|можете|'
                     r'мог бы|не мог бы ты|не мог бы|будь добр|будь добра|ты можешь|а ну|окей|ок|ладно|тогда|просто|'
                     r'мне нужно|мне надо|хочу|я хочу)\s+)+')
_QUESTION_START = re.compile(r'^(?:как|что|почему|зачем|где|когда|какой|какая|какие|какое|сколько|кто|чем|куда|откуда|'
                             r'чей|ли|why|how|what|who|where|when)\b')


def _strip(raw: str):
    """Возвращает (оригинал, нормализованная копия ТОЙ ЖЕ длины) без вводных слов и знаков в конце."""
    s = raw.strip().strip('"«»“”\'')
    t = s.lower().replace('ё', 'е')
    if len(t) != len(s):
        s = t
    m = _FILLER.match(t)
    if m:
        s, t = s[m.end():], t[m.end():]
    while t and t[-1] in '.!?… ,;':
        s, t = s[:-1], t[:-1]
    return s.strip(), t.strip()


def _num(t: str):
    m = re.search(r'\d+(?:[.,]\d+)?', t)
    return int(float(m.group(0).replace(',', '.'))) if m else None


def _clamp(v, lo=0, hi=100):
    return max(lo, min(hi, int(v)))


# ==================== ОТДЕЛЬНЫЕ КОМАНДЫ ====================
def _volume(t):
    if not re.search(r'громк|звук|volume|\bгромче\b|\bтише\b|\bпогромче\b|\bпотише\b|\bмьют\b|\bmute\b|заглуши', t):
        return None
    n = _num(t)
    if n is None and re.search(r'(?:выключи|отключи|убери|вырубь|заглуши|заглушить)(?:\s+\w+)?\s+(?:весь\s+)?(?:звук|громкость)|'
                               r'без звука|\bмьют\b|\bmute\b|заглуши', t):
        return Cmd('volume', {'mode': 'mute'}, 'Звук выключен')
    if n is None and re.search(r'(?:включи|верни|включить|врубай|включай|вруби)(?:\s+\w+)?\s+(?:звук|громкость)|размьют|unmute|со звуком', t):
        return Cmd('volume', {'mode': 'unmute'}, 'Звук включён')
    up = re.search(r'увеличь|прибавь|повысь|добавь|подними|громче|погромче|усиль', t)
    down = re.search(r'уменьши|убавь|снизь|понизь|тише|потише|приглуши|ослабь|опусти', t)
    small = re.search(r'\b(?:немного|чуть|чуть-чуть|слегка|капельку)\b', t)
    if n is not None:
        if re.search(r'\bдо\s+\d', t):
            return Cmd('volume', {'mode': 'set', 'value': _clamp(n)}, f'Громкость: {_clamp(n)}%')
        if (up or down) and re.search(r'\bна\s+\d', t):
            d = n if up and not down else -n
            return Cmd('volume', {'mode': 'delta', 'value': max(-100, min(100, d))}, f"Громкость {'+' if d > 0 else '−'}{abs(d)}%")
        return Cmd('volume', {'mode': 'set', 'value': _clamp(n)}, f'Громкость: {_clamp(n)}%')
    if re.search(r'максимум|на полную|до упора|на всю', t):
        return Cmd('volume', {'mode': 'set', 'value': 100}, 'Громкость: 100%')
    if re.search(r'минимум|на ноль', t):
        return Cmd('volume', {'mode': 'set', 'value': 0}, 'Громкость: 0%')
    if up or down:
        d = 5 if small else 10
        d = d if up and not down else -d
        return Cmd('volume', {'mode': 'delta', 'value': d}, f"Громкость {'+' if d > 0 else '−'}{abs(d)}%")
    return None


def _brightness(t):
    if not re.search(r'яркост|\bярче\b|\bпояр\w+\b|\bтемнее\b|\bподтемни\w*', t):
        return None
    n = _num(t)
    up = re.search(r'увеличь|прибавь|повысь|добавь|подними|ярче|поярче|усиль', t)
    down = re.search(r'уменьши|убавь|снизь|понизь|темнее|потемнее|приглуши|опусти', t)
    if n is not None:
        if re.search(r'\bдо\s+\d', t) or not ((up or down) and re.search(r'\bна\s+\d', t)):
            return Cmd('brightness', {'mode': 'set', 'value': _clamp(n)}, f'Яркость: {_clamp(n)}%')
        d = n if up and not down else -n
        return Cmd('brightness', {'mode': 'delta', 'value': d}, f"Яркость {'+' if d > 0 else '−'}{abs(d)}%")
    if re.search(r'максимум|на полную', t):
        return Cmd('brightness', {'mode': 'set', 'value': 100}, 'Яркость: 100%')
    if re.search(r'минимум', t):
        return Cmd('brightness', {'mode': 'set', 'value': 5}, 'Яркость: 5%')
    if up or down:
        d = 15 if up and not down else -15
        return Cmd('brightness', {'mode': 'delta', 'value': d}, f"Яркость {'+' if d > 0 else '−'}15%")
    return None


_V = r'(?:(?:включи|поставь|переключи|давай|запусти|сделай|вруби)\s+)?'
_MEDIA = (
    ('pause', rf'{_V}(?:на\s+)?пауз[ауы]?(?:\s+(?:музыку|трек|песню|плеер|воспроизведение))?|'
              r'(?:останови|выключи|поставь на паузу)\s+(?:музыку|трек|песню|плеер|воспроизведение)|стоп|стой'),
    ('play', r'(?:продолжи|продолжить|играй|воспроизведи|возобнови|плей|play)(?:\s+(?:музыку|трек|песню|плеер))?|'
             r'(?:включи|запусти|вруби|поставь)\s+(?:музыку|трек|песню|плеер)'),
    ('next', rf'{_V}(?:следующ\w+|дальше|скип|скипни|next)(?:\s+(?:трек|песн\w+|композици\w+))?|'
             r'(?:пропусти|переключи)\s+(?:трек|песню|композицию)'),
    ('prev', rf'{_V}(?:предыдущ\w+|прошл\w+)(?:\s+(?:трек|песн\w+|композици\w+))?|'
             r'(?:трек|песню)\s+назад|вернись\s+(?:на\s+)?(?:трек|песню)|prev'),
)
_MEDIA_LABEL = {'pause': 'Пауза', 'play': 'Воспроизведение', 'next': 'Следующий трек', 'prev': 'Предыдущий трек'}


def _media(t):
    for act, rx in _MEDIA:
        if re.fullmatch(rx, t):
            return Cmd('media', {'cmd': act}, _MEDIA_LABEL[act])
    return None


def _timer(t):
    if not re.search(r'таймер|засеки|секундомер', t):
        return None
    if re.search(r'останови|выключи|отмени|сбрось|сбросить|убери|отключи|стоп', t):
        return Cmd('timer_stop', {}, 'Таймер остановлен')
    secs = 0
    if re.search(r'полчаса|пол часа', t):
        secs += 1800
    if re.search(r'полтора\s+час', t):
        secs += 5400
    for n, unit in re.findall(r'(\d+)\s*(час\w*|ч\b|мин\w*|м\b|сек\w*|с\b)', t):
        n = int(n)
        secs += n * 3600 if unit.startswith(('час', 'ч')) else (n * 60 if unit.startswith('м') else n)
    if re.search(r'(?<!\d)(?<!\d )\bчас\b', t):                 # «на час», «час 30 минут» (а «1 час» уже посчитан выше)
        secs += 3600
    if not secs:
        return Cmd('timer', {'secs': None}, 'Таймер запущен')
    secs = min(secs, 24 * 3600)
    return Cmd('timer', {'secs': secs}, 'Таймер: ' + fmt_secs(secs))


def fmt_secs(secs: int) -> str:
    h, m, s = secs // 3600, secs % 3600 // 60, secs % 60
    parts = ([f'{h} ч'] if h else []) + ([f'{m} мин'] if m else []) + ([f'{s} с'] if s and not h else [])
    return ' '.join(parts) or '0 с'


def _reminder(raw, t):
    m = re.match(r'^(?:(?:поставь|создай|добавь|сделай|установи)\s+(?:мне\s+)?)?(?:напомни(?:ть)?|напоминани\w+)\b\s*(?:мне\s+)?(?:о том,?\s+что\s+|о том\s+|про\s+|что\s+)?', t)
    if not m:
        return None
    rest = raw[m.end():].strip(' :,-–—')
    return Cmd('reminder', {'raw': rest}, 'Напоминание')


def _note(raw, t):
    m = re.match(r'^(?:(создай|сделай|добавь|запиши|новая|новую|оставь|сохрани)\s+(?:мне\s+)?(?:быструю\s+|новую\s+)?)?'
                 r'(?:заметк\w*|записк\w*)\b\s*(?:что\s+|про\s+|о\s+|[:\-—])?\s*', t)
    if m and (m.group(1) or ':' in m.group(0)):
        return Cmd('note', {'text': raw[m.end():].strip(' :,-–—')}, 'Заметка')
    m = re.match(r'^запомни\s*,?\s*(?:что\s+)?', t)
    if m:
        return Cmd('note', {'text': raw[m.end():].strip(' :,-–—')}, 'Заметка')
    return None


def _tab_of(target: str):
    for stem, key in _TAB_WORDS:
        if target.startswith(stem):
            return key
    return None


def _domain(target: str):
    tld = {'ком': 'com', 'ру': 'ru', 'орг': 'org', 'нет': 'net', 'ио': 'io', 'ай': 'ai', 'инфо': 'info'}
    d = re.sub(r'\s+точка\s+(\w+)', lambda m: '.' + tld.get(m.group(1), m.group(1)), target.strip())
    d = re.sub(r'^(?:https?://)?(?:www\.)?', '', d)
    m = re.fullmatch(r'([a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.(?:[a-z]{2,24}|рф))(/\S*)?', d)
    if not m:
        return None
    url = f"https://{m.group(1)}{m.group(2) or ''}"
    return url if urlparse(url).hostname == m.group(1) else None


def _site(target: str):
    for names, val in SITES.items():
        if target in names:
            return val
    return None


def _builtin_app(target: str):
    for names, val in BUILTIN_APPS.items():
        if target in names:
            return val
    return None


_ENGINES = (('ютуб', 'https://www.youtube.com/results?search_query=', 'YouTube'), ('youtube', 'https://www.youtube.com/results?search_query=', 'YouTube'),
            ('яндекс', 'https://yandex.ru/search/?text=', 'Яндекс'), ('википеди', 'https://ru.wikipedia.org/w/index.php?search=', 'Википедия'),
            ('гугл', 'https://www.google.com/search?q=', 'Google'), ('google', 'https://www.google.com/search?q=', 'Google'),
            ('интернет', 'https://www.google.com/search?q=', 'Google'), ('сети', 'https://www.google.com/search?q=', 'Google'))


def _search(raw, t):
    m = re.match(r'^(загугли|погугли|гугли|найди|поищи|ищи|найти|искать)\s+(?:мне\s+)?(?:в\s+|на\s+)?(.+)$', t)
    if not m:
        return None
    verb, rest_t = m.group(1), m.group(2)
    rest = raw[m.start(2):]
    engine = None
    m2 = re.match(r'^(ютуб\w*|youtube|яндекс\w*|википеди\w*|гугл\w*|google|интернет\w*|сети)\s+(.+)$', rest_t)
    if m2:
        engine, rest = m2.group(1), raw[m.start(2) + m2.start(2):]
    else:
        m3 = re.match(r'^(.+?)\s+(?:в|на)\s+(ютубе|youtube|яндексе|википедии|гугле|google|интернете|сети)$', rest_t)
        if m3:
            engine, rest = m3.group(2), raw[m.start(2):m.start(2) + m3.end(1)]
    if engine is None and verb not in ('загугли', 'погугли', 'гугли'):
        return None                                            # «найди ошибку в коде» — это вопрос к ИИ, не поиск в браузере
    engine = engine or 'google'
    for stem, base, title in _ENGINES:
        if engine.startswith(stem):
            q = rest.strip()
            if not q:
                return None
            return Cmd('open_url', {'url': base + quote_plus(q)}, f'Поиск в {title}: {q[:40]}')
    return None


def _open(raw, t):
    m = re.match(r'^(?:открой|открыть|запусти|запустить|включи|покажи|зайди\s+(?:на|в)|перейди\s+(?:на|в|к)|перейти\s+(?:на|в)|'
                 r'go to|open)\s+(?:мне\s+)?(?:пожалуйста\s+)?(.+)$', t)
    if not m:
        m = re.match(r'^(?:вкладк\w*|раздел)\s+(.+)$', t)
        if not m:
            return None
    target = re.sub(r'^(?:вкладку|вкладка|раздел|страницу|страница)\s+', '', m.group(1)).strip()
    target = re.sub(r'\s+(?:в\s+браузере|в\s+хроме|в\s+chrome|в\s+edge|на\s+острове|в\s+острове)$', '', target)
    target = re.sub(r'^(?:сайт|сайта|ссылку|страницу|приложение|программу|программа)\s+', '', target).strip()
    target = re.sub(r'^(?:мои|мой|моё|мою|все)\s+', '', target)
    if not target:
        return None
    tab = _tab_of(target) if len(target.split()) <= 2 else None
    if tab:
        return Cmd('tab', {'tab': tab}, f'Открываю: {TAB_TITLES[tab]}')
    site = _site(target)
    if site:
        return Cmd('open_url', {'url': site[1]}, f'Открываю {site[0]}')
    dom = _domain(target)
    if dom:
        return Cmd('open_url', {'url': dom}, f"Открываю {urlparse(dom).hostname}")
    app = _builtin_app(target)
    if app:
        return Cmd('open_app', {'name': app[0], 'target': app[1], 'builtin': True}, f'Запускаю {app[0]}')
    if len(target.split()) <= 3 and not _QUESTION_START.match(target):
        return Cmd('open_app', {'name': target, 'target': '', 'builtin': False}, f'Запускаю {target}')
    return None


def _ui(raw, t):
    """Управление самим островом и Windows."""
    if re.fullmatch(r'(?:закрой|скрой|убери|сверни|спрячь)\s+(?:остров|чат|панель)|свернись|скройся|закрыть\s+остров', t):
        return Cmd('island_close', {}, 'Остров закрыт')
    if re.fullmatch(r'(?:закрепи|зафиксируй|не закрывай)\s*(?:остров|панель)?', t):
        return Cmd('island_pin', {'on': True}, 'Остров закреплён')
    if re.fullmatch(r'(?:открепи|отпусти|сними\s+закрепление)\s*(?:остров|панель)?', t):
        return Cmd('island_pin', {'on': False}, 'Остров откреплён')
    if re.search(r'(?:нов\w+\s+(?:чат|диалог|разговор))|(?:начни|начать|давай)\s+(?:заново|нов\w+\s+(?:чат|диалог))|очисти\s+чат', t):
        return Cmd('new_chat', {}, 'Новый диалог')
    if re.search(r'не\s+беспокоить', t):
        off = re.search(r'выключи|отключи|отмени|сними|убери|выйди|вкл\w*\s+не', t) and not re.search(r'^включи|^вруби|^активируй', t)
        return Cmd('dnd', {'on': not off}, 'Не беспокоить: ' + ('выкл' if off else 'вкл'))
    if re.search(r'(?:отметь|пометь)\s+(?:все\s+)?(?:уведомления\s+)?(?:как\s+)?прочитанн\w+|прочитай\s+все\s+уведомления', t):
        return Cmd('notif_read_all', {}, 'Уведомления прочитаны')
    if re.search(r'(?:очисти|удали|почисти)\s+(?:все\s+)?уведомления', t):
        return Cmd('notif_clear', {}, 'Уведомления очищены')
    if re.search(r'(?:темн\w+|светл\w+)\s+тем\w+|тем\w+\s+(?:темн\w+|светл\w+)|(?:смени|поменяй|переключи)\s+тему', t):
        if re.search(r'темн', t):
            return Cmd('theme', {'mode': 'dark'}, 'Тёмная тема')
        if re.search(r'светл', t):
            return Cmd('theme', {'mode': 'light'}, 'Светлая тема')
        return Cmd('theme', {'mode': 'toggle'}, 'Тема переключена')
    if re.search(r'(?:распознай|считай|скопируй|вытащи)\s+текст(?:\s+(?:с|на)\s+экран\w*)?$|^ocr$', t):
        return Cmd('ocr', {}, 'Распознавание текста')
    if re.fullmatch(r'(?:сделай\s+)?(?:скриншот|снимок)(?:\s+экрана)?', t):
        return Cmd('shot_full', {}, 'Скриншот')
    if re.fullmatch(r'(?:сделай\s+)?(?:скриншот|снимок)\s+(?:области|части)|выдели\s+область', t):
        return Cmd('shot_area', {}, 'Скриншот области')
    if re.fullmatch(r'(?:заблокируй|заблокировать|блокировка)(?:\s+(?:компьютер|экран|пк|windows))?|lock', t):
        return Cmd('lock', {}, 'Блокировка')
    return None


def _ask_ctx(raw, t):
    """Вопросы про экран и буфер: уходят в чат вместе со скриншотом или текстом буфера."""
    if re.search(r'(?:что|чего)\s+(?:сейчас\s+)?(?:на|в)\s+экран\w*|(?:проанализируй|опиши|объясни|разбери|посмотри|глянь|оцени)\b.*\b(?:экран|скриншот|окно)\w*|'
                 r'(?:посмотри|глянь)\s+на\s+экран', t):
        return Cmd('ask_screen', {'q': raw}, 'Анализ экрана')
    if re.search(r'(?:прочитай|распознай)\s+текст\s+(?:с|на)\s+экран\w*\s+и\s+\w+', t):
        return Cmd('ask_ocr', {'q': raw}, 'Текст с экрана → ИИ')
    if re.search(r'(?:что|чего)\s+(?:сейчас\s+)?(?:в|у меня в)\s+буфер\w*|(?:объясни|переведи|проанализируй|разбери|перескажи|исправь|суммируй|кратко)\b.*\b(?:буфер|скопированн\w+|выделенн\w+)|'
                 r'(?:что\s+)?(?:я\s+)?(?:только\s+)?скопировал\w*', t):
        return Cmd('ask_clip', {'q': raw}, 'Буфер → ИИ')
    return None


def _local_info(t):
    if re.fullmatch(r'который\s+час|сколько\s+(?:сейчас\s+)?времени|сколько\s+время|время|сколько\s+на\s+часах|текущее\s+время', t):
        return Cmd('time', {}, 'Время')
    if re.fullmatch(r'какое\s+(?:сегодня\s+)?число(?:\s+сегодня)?|какая\s+(?:сегодня\s+)?дата|какой\s+(?:сегодня\s+)?день(?:\s+недели)?|дата|число\s+сегодня|что\s+за\s+день', t):
        return Cmd('date', {}, 'Дата')
    if re.fullmatch(r'что\s+(?:сейчас\s+)?играет|какая\s+(?:сейчас\s+)?(?:песня|музыка|композиция)(?:\s+играет)?|что\s+за\s+(?:трек|песня)(?:\s+играет)?', t):
        return Cmd('media_info', {}, 'Сейчас играет')
    return None


def _dictate(raw, t):
    m = re.match(r'^(?:надиктуй|в\s+буфер|скопируй\s+в\s+буфер|скопируй)\s*[:\-—]?\s+(.+)$', t)
    if m:
        return Cmd('dictate', {'text': raw[m.start(1):].strip()}, 'В буфер')
    return None


def parse(raw: str):
    """Фраза → Cmd или None (тогда это обычный вопрос к ИИ)."""
    if not raw or not raw.strip():
        return None
    raw, t = _strip(raw)
    if not t:
        return None
    t_num = words_to_digits(t)
    raw_num = raw if t_num == t else t_num                   # числа прописью → цифры (длина меняется, оригинал не нужен)
    for fn in (lambda: _local_info(t), lambda: _ask_ctx(raw, t)):
        c = fn()
        if c:
            return c
    if _QUESTION_START.match(t):
        return None
    for fn in (lambda: _reminder(raw_num, t_num), lambda: _note(raw, t), lambda: _timer(t_num), lambda: _volume(t_num),
               lambda: _brightness(t_num), lambda: _media(t), lambda: _ui(raw, t), lambda: _dictate(raw, t),
               lambda: _search(raw, t), lambda: _open(raw, t)):
        c = fn()
        if c:
            return c
    return None
