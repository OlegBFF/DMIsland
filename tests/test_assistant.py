import os
import tempfile
import unittest
from core.commands import parse, words_to_digits
from core.db import Database
from core.notif_extract import actions_for, find_code, find_image_refs, find_urls, group_by_app, group_summary, queue_groups
from core.notif_media import sniff_image
from core.stores import ChatStore, NotificationStore
from core.vad import Endpointer
from modules.ai_client import build_payload
from modules.app_finder import find_shortcut
from modules.chat_logic import build_model_history, has_context


class CommandsTest(unittest.TestCase):
    def a(self, text):
        c = parse(text)
        return (c.action, c.args) if c else None

    def test_volume(self):
        self.assertEqual(self.a('Уменьши громкость до 30%'), ('volume', {'mode': 'set', 'value': 30}))
        self.assertEqual(self.a('громкость 50'), ('volume', {'mode': 'set', 'value': 50}))
        self.assertEqual(self.a('увеличь громкость на 10'), ('volume', {'mode': 'delta', 'value': 10}))
        self.assertEqual(self.a('убавь звук на 15 процентов'), ('volume', {'mode': 'delta', 'value': -15}))
        self.assertEqual(self.a('сделай потише'), ('volume', {'mode': 'delta', 'value': -10}))
        self.assertEqual(self.a('выключи звук'), ('volume', {'mode': 'mute'}))
        self.assertEqual(self.a('включи звук'), ('volume', {'mode': 'unmute'}))
        self.assertEqual(self.a('громкость на максимум'), ('volume', {'mode': 'set', 'value': 100}))
        self.assertEqual(self.a('эй остров, пожалуйста сделай громкость тридцать пять'), ('volume', {'mode': 'set', 'value': 35}))
        self.assertEqual(self.a('убавь громкость до двадцати пяти'), ('volume', {'mode': 'set', 'value': 25}))
        self.assertEqual(self.a('громкость 250')[1]['value'], 100)

    def test_words_to_digits(self):
        self.assertEqual(words_to_digits('сто двадцать пять'), '125')
        self.assertEqual(words_to_digits('пять пять'), '5 5')

    def test_media_timer(self):
        self.assertEqual(self.a('следующий трек'), ('media', {'cmd': 'next'}))
        self.assertEqual(self.a('пауза'), ('media', {'cmd': 'pause'}))
        self.assertEqual(self.a('включи музыку'), ('media', {'cmd': 'play'}))
        self.assertEqual(self.a('таймер на 10 минут'), ('timer', {'secs': 600}))
        self.assertEqual(self.a('поставь таймер на час 30 минут'), ('timer', {'secs': 5400}))
        self.assertEqual(self.a('таймер на полчаса'), ('timer', {'secs': 1800}))
        self.assertEqual(self.a('останови таймер')[0], 'timer_stop')

    def test_reminder_note(self):
        a = self.a('напомни через 15 минут позвонить маме')
        self.assertEqual(a, ('reminder', {'raw': 'через 15 минут позвонить маме'}))
        self.assertEqual(self.a('напомни через пятнадцать минут выйти')[1]['raw'], 'через 15 минут выйти')
        self.assertEqual(self.a('создай заметку купить молоко'), ('note', {'text': 'купить молоко'}))
        self.assertEqual(self.a('Заметка: Идея для бота'), ('note', {'text': 'Идея для бота'}))
        self.assertEqual(self.a('запомни, что ключи в ящике'), ('note', {'text': 'ключи в ящике'}))

    def test_open(self):
        self.assertEqual(self.a('открой ютуб'), ('open_url', {'url': 'https://www.youtube.com'}))
        self.assertEqual(self.a('открой сайт github.com'), ('open_url', {'url': 'https://github.com'}))
        self.assertEqual(self.a('открой github точка ком')[1]['url'], 'https://github.com')
        self.assertEqual(self.a('открой блокнот')[0], 'open_app')
        self.assertEqual(self.a('открой телеграм')[1]['builtin'], False)
        self.assertEqual(self.a('открой заметки'), ('tab', {'tab': 'notes'}))
        self.assertEqual(self.a('загугли курс доллара')[1]['url'], 'https://www.google.com/search?q=%D0%BA%D1%83%D1%80%D1%81+%D0%B4%D0%BE%D0%BB%D0%BB%D0%B0%D1%80%D0%B0')
        self.assertIn('youtube.com/results', self.a('поищи котиков в ютубе')[1]['url'])

    def test_not_commands_go_to_ai(self):
        for t in ('привет, как дела', 'как открыть блокнот в windows?', 'найди ошибку в моём коде', 'что такое громкость',
                  'открой мне статью про питон и аиогрaм', 'напиши функцию сортировки', 'расскажи анекдот', ''):
            self.assertIsNone(parse(t), t)

    def test_unsafe_urls_never_built(self):
        for t in ('открой javascript:alert(1)', 'открой file:///c:/windows', 'открой user@evil.com/x'):
            c = parse(t)
            self.assertFalse(c and c.action == 'open_url' and not c.args['url'].startswith('https://'))
        self.assertNotEqual((parse('открой user@evil.com') or parse('x')) and (parse('открой user@evil.com').args.get('url')), 'https://user@evil.com')

    def test_ui_and_context(self):
        self.assertEqual(self.a('закрой остров')[0], 'island_close')
        self.assertEqual(self.a('новый чат')[0], 'new_chat')
        self.assertEqual(self.a('включи не беспокоить'), ('dnd', {'on': True}))
        self.assertEqual(self.a('выключи не беспокоить'), ('dnd', {'on': False}))
        self.assertEqual(self.a('тёмная тема'), ('theme', {'mode': 'dark'}))
        self.assertEqual(self.a('что на экране?')[0], 'ask_screen')
        self.assertEqual(self.a('объясни что в буфере')[0], 'ask_clip')
        self.assertEqual(self.a('распознай текст с экрана')[0], 'ocr')
        self.assertEqual(self.a('который час')[0], 'time')
        self.assertEqual(self.a('надиктуй привет всем'), ('dictate', {'text': 'привет всем'}))


class NotifExtractTest(unittest.TestCase):
    def test_links_codes(self):
        t = 'Смотри https://example.com/a.png, и www.site.ru/x. Ваш код: 482913'
        self.assertEqual(find_urls(t), ['https://example.com/a.png', 'https://www.site.ru/x'])
        self.assertEqual(find_code(t), '482913')
        self.assertEqual(find_code('Ваш код 1234'), '1234')
        self.assertEqual(find_code('Заказ 12 на сумму 2024 руб'), None)
        self.assertEqual(find_urls('javascript:alert(1) ftp://x.com'), [])

    def test_image_refs(self):
        t = r'фото https://x.com/p.JPG и файл C:\Users\me\Pictures\cat.png и https://x.com/page'
        self.assertEqual(find_image_refs(t), [('url', 'https://x.com/p.JPG'), ('file', r'C:\Users\me\Pictures\cat.png')])

    def test_actions(self):
        n = {'app': 'Telegram', 'app_id': 'tg', 'title': 'Аня', 'body': 'глянь https://ya.ru код 5566'}
        keys = [a['key'] for a in actions_for(n, can_reply=True)]
        self.assertEqual(keys, ['reply', 'copy_code', 'link'])
        spot = {'app': 'Spotify', 'app_id': 'spotify', 'title': 'Трек', 'body': 'Исполнитель'}
        self.assertEqual([a['key'] for a in actions_for(spot)], ['music'])

    def test_groups(self):
        items = [{'app': 'TG', 'app_id': 'tg', 'read': 0, 'priority': 'important'}, {'app': 'Mail', 'app_id': 'mail', 'read': 1},
                 {'app': 'TG', 'app_id': 'TG', 'read': 1}]
        g = group_by_app(items)
        self.assertEqual([(k, len(x)) for k, _, x in g], [('tg', 2), ('mail', 1)])
        self.assertEqual(group_summary(g[0][2]), {'total': 2, 'unread': 1, 'priority': 'important'})
        self.assertEqual(queue_groups(items), [('tg', [0, 2]), ('mail', [1])])

    def test_sniff(self):
        self.assertEqual(sniff_image(b'\x89PNG\r\n\x1a\nxxxx'), 'png')
        self.assertIsNone(sniff_image(b'<svg onload=alert(1)>'))


class StoreGroupTest(unittest.TestCase):
    def test_app_actions_cyrillic(self):
        st = NotificationStore(Database(':memory:'))
        for i, app in enumerate(('Сообщения', 'Сообщения', 'Почта')):
            st.add('test', '', app, f't{i}', 'b', 'normal')
        st.mark_read_app('сообщения')
        self.assertEqual(sum(1 for n in st.items() if n['read']), 2)
        st.delete_app('СООБЩЕНИЯ')
        self.assertEqual([n['app'] for n in st.items()], ['Почта'])


class ChatLogicTest(unittest.TestCase):
    def test_history_for_model(self):
        d = tempfile.mkdtemp()
        p1, p2 = os.path.join(d, 'a.jpg'), os.path.join(d, 'b.jpg')
        for p in (p1, p2):
            with open(p, 'wb') as f:
                f.write(b'img')
        msgs = [
            {'role': 'user', 'content': 'громкость 30', 'attach': [{'kind': 'cmd'}]},
            {'role': 'action', 'content': 'Громкость: 30%'},
            {'role': 'user', 'content': 'что тут?', 'attach': [{'kind': 'shot', 'path': p1}]},
            {'role': 'assistant', 'content': 'окно'},
            {'role': 'user', 'content': 'объясни', 'attach': [{'kind': 'clip', 'text': 'abc'}, {'kind': 'shot', 'path': p2}]},
        ]
        h = build_model_history(msgs, load_image=lambda p: 'data:' + os.path.basename(p))
        self.assertEqual([m['role'] for m in h], ['user', 'assistant', 'user'])
        self.assertNotIn('images', h[0])
        self.assertIn('больше недоступен', h[0]['content'])
        self.assertEqual(h[2]['images'], ['data:b.jpg'])
        self.assertIn('abc', h[2]['content'])
        self.assertTrue(has_context(msgs))
        self.assertFalse(has_context(msgs[:2]))

    def test_payload_with_image(self):
        pl = build_payload('m', 'sys', [{'role': 'user', 'content': 'q', 'images': ['data:image/jpeg;base64,AA']}], 10000, True)
        c = pl['messages'][1]['content']
        self.assertEqual(c[0], {'type': 'text', 'text': 'q'})
        self.assertEqual(c[1]['image_url']['url'], 'data:image/jpeg;base64,AA')

    def test_store_attach_roundtrip(self):
        st = ChatStore(Database(':memory:'))
        cid = st.new_conv()
        st.add(cid, 'user', 'q', [{'kind': 'ocr', 'label': 'Текст', 'text': 'привет'}])
        st.add(cid, 'assistant', 'a')
        m = st.messages(cid)
        self.assertEqual(m[0]['attach'][0]['text'], 'привет')
        self.assertNotIn('attach', m[1])


class VadFinderTest(unittest.TestCase):
    def test_endpointer(self):
        e = Endpointer()
        res = [e.feed(100, 0.1) for _ in range(5)] + [e.feed(5000, 0.1) for _ in range(4)] + [e.feed(100, 0.1) for _ in range(12)]
        self.assertIn('speech', res)
        self.assertEqual(res.count('done') > 0, True)
        e2 = Endpointer(wait_max=1.0)
        self.assertEqual([e2.feed(100, 0.2) for _ in range(6)][-1], 'timeout')

    def test_find_shortcut(self):
        d = tempfile.mkdtemp()
        for n in ('Telegram.lnk', 'Telegram Uninstall.lnk', 'Discord Canary.lnk'):
            open(os.path.join(d, n), 'w').close()
        self.assertTrue(find_shortcut('telegram', [d]).endswith('Telegram.lnk'))
        self.assertTrue(find_shortcut('canary', [d]).endswith('Discord Canary.lnk'))
        self.assertIsNone(find_shortcut('zzz', [d]))


if __name__ == '__main__':
    unittest.main()
