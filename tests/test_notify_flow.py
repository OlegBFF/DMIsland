"""Сценарии центра уведомлений на «поддельном» острове: политика показа, очередь, отложенные, сводка, ответ."""
import time
import unittest
from datetime import datetime, timedelta

from tests.qt_stub import install
install()

from core.db import Database                                   # noqa: E402
from modules.notify_center import MAX_QUEUE, NotifyMixin       # noqa: E402
from modules.notify_reply import ReplyProvider                 # noqa: E402


class FakeCard:
    def __init__(self):
        self.items, self.replying, self.progress, self.hidden = [], False, 1.0, False
        self.previews = {}

    def set_items(self, items, idx=0):
        self.items = list(items)

    def cancel_reply(self, silent=False):
        self.replying = False

    def hide(self):
        self.hidden = True

    def preferred_height(self):
        return 150


class FakeTabs:
    def __init__(self):
        self.badge = None

    def set_badge(self, idx, count, color):
        self.badge = (idx, count)

    def update(self):
        pass


class Echo(ReplyProvider):
    name = 'echo'

    def can_reply(self, n):
        return True

    def send(self, n, text):
        self.last = text
        return True, 'ok'


class Host(NotifyMixin):
    def __init__(self, cfg=None):
        self.cfg = dict(cfg or {})
        self.db = Database(':memory:')
        self.fs = self.app_hidden = False
        self.mode = 'idle'
        self.until = self.leave = 0.0
        self.frame_ms_v = 16
        self.popped, self.typing = [], []
        self.tabs = FakeTabs()
        self.recorder = type('R', (), {'recording': False})()
        self.anim_timer = type('T', (), {'setInterval': lambda self, v: None})()
        # init_notify создаёт Qt-объекты; здесь подменяем нужное вручную
        from core.stores import NotificationStore
        from modules.notify_reply import ReplyRegistry
        self.notifs = NotificationStore(self.db)
        self.replies = ReplyRegistry()
        self.nq, self.ncur, self.nicons, self.notif_total, self.nstatus = [], 0, {}, 6.0, 'init'
        self._backlog, self._nf_sig, self._notif_prune_t, self._notif_unread = [], None, 0.0, {}
        self.card = FakeCard()
        self._full_images = {}
        self.listener = type('L', (), {'remove': lambda self, i: setattr(self, 'removed', i)})()

    def chat_hold(self):
        return False

    def pop(self, title, sub='', ic=None, secs=3.2):
        self.popped.append((title, sub, secs))

    def set_typing(self, on):
        self.typing.append(on)

    def refresh_notifs(self):
        pass

    def feed(self, app='Telegram', title='Аня', body='Привет', app_id='tg', win_id=None):
        self.on_win_notification({'app': app, 'app_id': app_id, 'title': title, 'body': body, 'win_id': win_id, 'icon': None})


class Flow(unittest.TestCase):
    def test_important_message_opens_card(self):
        h = Host()
        h.feed(body='Срочно позвони')
        self.assertEqual(h.mode, 'notif')
        self.assertEqual(h.card.items[0]['priority'], 'important')
        self.assertEqual(h.card.items[0]['title'], 'Аня')
        self.assertEqual(h.tabs.badge, (8, 1))
        self.assertGreater(h.until, time.time() + 10)                    # важное висит дольше обычного

    def test_normal_goes_to_toast_system_too(self):
        h = Host()
        h.feed(app='Chrome', app_id='chrome', title='Новости', body='Курс валют')
        self.assertEqual(h.mode, 'idle')
        self.assertEqual(h.popped[0][0], 'Новости')
        self.assertEqual(h.nq, [])
        h.popped.clear()
        h.feed(app='Параметры', app_id='windows.immersivecontrolpanel', title='Обновление', body='Готово')
        self.assertEqual(h.card.items, [])
        self.assertEqual(h.popped[0][0], 'Обновление')

    def test_silent_modes(self):
        h = Host({'notif_normal': 'silent'})
        h.feed(app='Chrome', app_id='chrome', title='Новости')
        self.assertEqual((h.popped, h.mode), ([], 'idle'))
        self.assertEqual(h.notifs.unread_counts()['normal'], 1)           # но в истории и в счётчике есть
        h2 = Host({'notif_enabled': False})
        h2.feed()
        self.assertEqual(h2.notifs.items(), [])

    def test_muted_app_is_not_even_stored(self):
        h = Host({'notif_muted_apps': 'spotify'})
        h.feed(app='Spotify', app_id='spotify.exe', title='Новый трек')
        self.assertEqual(h.notifs.items(), [])

    def test_dnd_blocks_normal_not_important(self):
        h = Host({'notif_dnd': True})
        h.feed(app='Chrome', app_id='chrome', title='Новости')
        self.assertEqual(h.mode, 'idle')
        h.feed()
        self.assertEqual(h.mode, 'notif')

    def test_open_panel_is_not_interrupted(self):
        h = Host()
        h.mode = 'open'
        h.feed()
        self.assertEqual((h.mode, h.nq), ('open', []))
        self.assertEqual(h.tabs.badge, (8, 1))                            # только бейдж на вкладке

    def test_queue_and_navigation(self):
        h = Host()
        for i in range(MAX_QUEUE + 2):
            h.feed(title=f'Контакт {i}', body=f'сообщение {i}')
        self.assertEqual(len(h.nq), MAX_QUEUE)
        self.assertEqual(h.nq[h.ncur]['title'], f'Контакт {MAX_QUEUE + 1}')   # показывается самое свежее
        first = h.ncur
        h._card_nav(1)
        self.assertNotEqual(h.ncur, first)
        nid = h.nq[h.ncur]['id']
        h._remove_from_queue(nid)
        self.assertEqual(len(h.nq), MAX_QUEUE - 1)
        for n in list(h.nq):
            h._remove_from_queue(n['id'])
        self.assertEqual(h.mode, 'idle')                                  # очередь пуста — остров сворачивается

    def test_repeat_notification_does_not_spawn_new_card(self):
        h = Host()
        h.feed(win_id=5)
        h.feed(win_id=5)
        self.assertEqual(len(h.nq), 1)
        self.assertEqual(len(h.notifs.items()), 1)

    def test_fullscreen_backlog_summary(self):
        h = Host()
        h.fs = True
        h.feed(title='А')
        h.feed(app='Chrome', app_id='chrome', title='Б')
        self.assertEqual((h.mode, h.popped), ('idle', []))
        self.assertEqual(len(h._backlog), 2)
        h.fs = False
        h.flush_backlog()
        self.assertEqual(h.popped[0][0], 'Пока вы были заняты')
        self.assertIn('важных: 1', h.popped[0][1])
        self.assertEqual(h._backlog, [])

    def test_snooze_then_return(self):
        h = Host()
        h.feed()
        n = h.nq[0]
        h.notif_snooze(n, datetime.now() + timedelta(seconds=1))
        self.assertEqual(h.mode, 'idle')                                  # карточка закрылась
        self.assertEqual(h.notifs.unread_counts()['important'], 0)
        h.check_notif_timers()
        self.assertEqual(h.mode, 'idle')                                  # ещё не время
        h.notifs.snooze(n['id'], time.time() - 1)
        h.check_notif_timers()
        self.assertEqual(h.mode, 'notif')                                 # вернулось
        self.assertEqual(h.notifs.unread_counts()['important'], 1)

    def test_reply_marks_read_and_closes(self):
        h = Host()
        h.replies.register(Echo())
        h.feed()
        n = h.nq[0]
        h._card_replied(n, 'Уже иду')
        self.assertEqual(h.replies.providers[0].last, 'Уже иду')
        self.assertEqual(h.notifs.unread_counts()['important'], 0)
        self.assertEqual((h.mode, h.nq), ('idle', []))
        self.assertEqual(h.popped[-1][0], 'Ответ')
        self.assertIn(False, h.typing)                                    # клавиатурный фокус возвращён

    def test_read_removes_from_windows_when_enabled(self):
        h = Host({'notif_clear_windows': True})
        h.feed(win_id=42)
        h.notif_read(h.nq[0])
        self.assertEqual(h.listener.removed, 42)

    def test_system_events_recorded_as_read(self):
        h = Host()
        h.record_system('USB подключён', 'E:')
        item = h.notifs.items()[0]
        self.assertEqual((item['priority'], item['read'], item['source']), ('system', 1, 'island'))
        self.assertEqual(h.notifs.unread_counts()['system'], 0)


if __name__ == '__main__':
    unittest.main()
