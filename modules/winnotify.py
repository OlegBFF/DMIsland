"""Чтение уведомлений Windows (UserNotificationListener) в фоновом потоке. К Qt-виджетам не прикасается — только сигналы."""
import asyncio
import threading
from PySide6.QtCore import QObject, Signal
from core.utils import log
from system.util import wr


def diff_new(seen: set, ids: list):
    """(новые id в порядке прихода, новое множество увиденных). Исчезнувшие из центра Windows id забываются."""
    return [i for i in ids if i not in seen], set(ids)


def split_texts(texts):
    """Первое текстовое поле тоста — заголовок (у мессенджеров это отправитель), остальные — текст."""
    texts = [t for t in (texts or []) if t is not None]
    if not texts:
        return '', ''
    return texts[0].strip(), '\n'.join(t.strip() for t in texts[1:] if t.strip())


class WinNotificationListener(QObject):
    received = Signal(dict)       # app, app_id, title, body, win_id, icon (bytes | None), time
    status = Signal(str)          # allowed | denied | error

    def __init__(s):
        super().__init__()
        s._stop = threading.Event()
        s._remove, s._lock = [], threading.Lock()
        s._thread = None
        s.state = 'init'

    def start(s):
        if s._thread is None:
            s._thread = threading.Thread(target=lambda: asyncio.run(s._main()), name='island-notify', daemon=True)
            s._thread.start()

    def stop(s):
        s._stop.set()

    def remove(s, win_id):
        """Убрать уведомление из центра Windows (вызывается из главного потока, выполняется в потоке слушателя)."""
        if win_id is not None:
            with s._lock:
                s._remove.append(int(win_id))

    def _set(s, state):
        if state != s.state:
            s.state = state
            s.status.emit(state)

    async def _main(s):
        while not s._stop.is_set():
            try:
                await s._session()
            except Exception as ex:
                log(f"notify listener: {ex!r}")
                s._set('error')
                await asyncio.sleep(10)

    async def _session(s):
        N = wr('windows.ui.notifications.management')
        U = wr('windows.ui.notifications')
        listener = N.UserNotificationListener.current
        access = await listener.request_access_async()
        if int(getattr(access, 'value', access)) != 1:                  # 1 = Allowed
            s._set('denied')
            await asyncio.sleep(20)                                      # пользователь может разрешить позже — спросим снова
            return
        s._set('allowed')
        seen, first, icons = set(), True, set()
        while not s._stop.is_set():
            items = list(await listener.get_notifications_async(U.NotificationKinds.TOAST))
            new_ids, seen = diff_new(seen, [int(n.id) for n in items])
            if first:
                first = False                                            # то, что уже висело в центре Windows, не «приходит» заново
            else:
                for n in items:
                    if int(n.id) in new_ids:
                        d = await s._extract(n, U, icons)
                        if d:
                            s.received.emit(d)
            with s._lock:
                gone, s._remove = s._remove, []
            for wid in gone:
                try:
                    listener.remove_notification(wid)
                except Exception as ex:
                    log(f"notify remove: {ex!r}")
            await asyncio.sleep(1.0)

    async def _extract(s, n, U, icons):
        try:
            info = n.app_info
            app, app_id = info.display_info.display_name, info.app_user_model_id
            texts = []
            try:
                binding = n.notification.visual.get_binding(U.KnownNotificationBindings.toast_generic)
                texts = [t.text for t in binding.get_text_elements()]
            except Exception:
                pass
            title, body = split_texts(texts)
            icon = None
            if app_id not in icons:                                      # логотип приложения берём один раз на приложение
                icons.add(app_id)
                icon = await s._logo(info)
            try:
                ts = n.creation_time.timestamp()
            except Exception:
                ts = None
            return {'app': app, 'app_id': app_id, 'title': title, 'body': body, 'win_id': int(n.id), 'icon': icon, 'time': ts}
        except Exception as ex:
            log(f"notify extract: {ex!r}")
            return None

    @staticmethod
    async def _logo(info):
        try:
            from winrt.windows.foundation import Size
            from winrt.windows.storage.streams import DataReader
            stream = await info.display_info.get_logo(Size(64, 64)).open_read_async()
            reader = DataReader(stream)
            await reader.load_async(int(stream.size))
            buf = bytearray(int(stream.size))
            reader.read_bytes(buf)
            return bytes(buf)
        except Exception:
            return None
