"""Быстрый ответ на уведомление.

Windows не даёт стороннему приложению ответить от имени другого: у UserNotificationListener нет доступа к кнопкам
и полям ответа чужого тоста. Поэтому ответ устроен через провайдеров: каждый сам решает, умеет ли он отвечать на
данное уведомление, и как. Встроен провайдер «открыть приложение и подготовить ответ»; настоящие провайдеры
(например, для мессенджера с собственным API) добавляются в ReplyRegistry без правок интерфейса.
"""
import re
import subprocess
import threading
import time

_AUMID = re.compile(r'^[\w.!\-+ ]{3,200}$')


class ReplyProvider:
    name = ''
    placeholder = 'Ответ…'

    def can_reply(self, n: dict) -> bool:
        return False

    def send(self, n: dict, text: str):
        """Возвращает (успех, сообщение для пользователя)."""
        return False, 'Не поддерживается'


def open_app(app_id: str) -> bool:
    """Запускает/активирует приложение по AUMID (работает для магазинных приложений и зарегистрированных в «Пуск»)."""
    if not app_id or not _AUMID.match(app_id):
        return False
    try:
        subprocess.Popen(['explorer.exe', f'shell:AppsFolder\\{app_id}'])
        return True
    except OSError:
        return False


class OpenAndCopyProvider(ReplyProvider):
    """Открывает приложение, а ответ кладёт в буфер (при включённой опции ещё и вставляет Ctrl+V).
    Автоматически НЕ отправляет — человек сам нажимает Enter в нужном чате."""
    name = 'open-and-copy'
    placeholder = 'Ответ скопируется, приложение откроется…'

    def __init__(self, copy_fn, paste_fn=None, autopaste=lambda: False):
        self.copy_fn, self.paste_fn, self.autopaste = copy_fn, paste_fn, autopaste

    def can_reply(self, n):
        return n.get('source') == 'windows' and bool(n.get('app_id'))

    def send(self, n, text):
        self.copy_fn(text)
        opened = open_app(n.get('app_id', ''))
        if opened and self.autopaste() and self.paste_fn:
            threading.Thread(target=lambda: (time.sleep(1.2), self.paste_fn()), daemon=True).start()
            return True, 'Приложение открыто, ответ вставляется'
        return True, ('Ответ скопирован — вставьте его в чате (Ctrl+V)' if opened else 'Ответ скопирован, приложение открыть не удалось')


class ReplyRegistry:
    def __init__(self, providers=()):
        self.providers = list(providers)

    def register(self, provider, first=True):
        self.providers.insert(0 if first else len(self.providers), provider)

    def find(self, n):
        return next((p for p in self.providers if p.can_reply(n)), None)

    def reply(self, n, text):
        p = self.find(n)
        if p is None:
            return False, 'Для этого приложения ответ недоступен'
        return p.send(n, text.strip())
