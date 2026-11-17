"""ИИ-ассистент: диалог с историей и потоковым выводом, команды голосом и текстом, командная строка."""
import ctypes
import re
import subprocess
import threading
import time
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPixmap
from PySide6.QtWidgets import QInputDialog
from core.commands import parse
from core.security import dpapi_decrypt, safe_math_eval, safe_open_path
from modules.ai_client import CONTEXT_NOTE, DEFAULT_SYSTEM, AIClient
from modules.assistant_ctx import default_prompt
from modules.chat_logic import build_model_history, has_context
from ui.image_viewer import ImageViewer
from ui.themes import STYLE

CHAT_TAB = 4


class AssistantMixin:
    """Часть класса Island: AssistantMixin."""

    # ==================== ИНИЦИАЛИЗАЦИЯ ====================
    def init_assistant(s):
        s.ai_token, s.ai_cancel, s.ai_busy, s.ai_partial = 0, None, False, []
        s._ai_bubble, s._last_sent = None, None
        s.chat_conv = s.chats.latest_conv()
        s.chat_msgs = s.chats.messages(s.chat_conv) if s.chat_conv else []

    def ai_client(s):
        return AIClient(s.cfg.get('ai_url', ''), dpapi_decrypt(s.cfg.get('ai_key_enc', '')), s.cfg.get('ai_model', 'gpt-4o-mini'))

    def tx_ai(s, prompt_prefix):
        txt = s.txt_ed.toPlainText().strip()
        if txt:
            s.query_ai(f"{prompt_prefix}\n\n{txt}", to_text_tab=True)

    def query_ai(s, prompt, to_text_tab=True):
        """Разовый запрос вне диалога (вкладка «Текст»): без истории, результат целиком."""
        client = s.ai_client()

        def run():
            try:
                ans = client.complete([{'role': 'user', 'content': prompt}], system='', max_chars=60000)
                s.aiReplySignal.emit('TXT:' + ans)
            except Exception as e:
                s.aiReplySignal.emit(f"ERR:{e}")
        threading.Thread(target=run, daemon=True).start()

    def on_ai_reply(s, msg):
        if msg.startswith('DRAFT:'):
            nid, _, text = msg[6:].partition(':')
            if s._draft_nid == int(nid):
                s.card.set_draft(text)
        elif msg.startswith('DRAFTERR:'):
            s.card.set_draft('')
            s.pop('ИИ не ответил', msg[9:70], (QColor('#ff453a'), 'chat'), 4.0)
        elif msg.startswith('TXT:'):
            s.txt_ed.setPlainText(msg[4:])
            s.pop('ИИ готов', 'Текст обновлён', (STYLE['acc'], 'chat'))
        else:
            s.pop('Ошибка ИИ', msg[4:70], (QColor('#ff453a'), 'chat'), 5.0)

    # ==================== ОСТРОВ НЕ ЗАКРЫВАЕТСЯ В ЧАТЕ ====================
    def chat_hold(s) -> bool:
        """Пока открыта вкладка «Чат», остров не сворачивается ни от клика вне острова, ни от ухода курсора:
        закрыть можно кнопкой ▾ в шапке, клавишей Esc или командой «закрой остров»."""
        return bool(s.cfg.get('chat_keep_open', True)) and s.stack.currentIndex() == CHAT_TAB

    def close_island(s):
        s.set_typing(False)
        s.tabs.pinned, s.tabs.idx = False, 0
        s.switch(0)                                   # следующее открытие — с главной, иначе чат снова удержит остров
        s.mode, s.leave = 'idle', 0
        s.tabs.update()

    # ==================== ВЫВОД В ЛЕНТУ ====================
    def display_attach(s, m):
        return [a for a in (m.get('attach') or []) if a.get('kind') != 'cmd']

    def render_chat(s):
        v = s.chat_view
        v.clear()
        for m in s.chat_msgs:
            if m['role'] == 'user':
                v.add('user', m['content'], s.display_attach(m))
            elif m['role'] == 'assistant':
                v.add('assistant', m['content'])
            elif m['role'] == 'action':
                v.add('action', m['content'], m.get('ok', True))
        s._ai_bubble = None
        s.chat_header_refresh()

    def chat_header_refresh(s):
        title = ''
        for m in s.chat_msgs:
            if m['role'] == 'user' and m['content'].strip():
                title = m['content'].strip().replace('\n', ' ')
                break
        model = s.cfg.get('ai_model', '')
        s.chat_head.set_info(title, model)
        has_key = bool(dpapi_decrypt(s.cfg.get('ai_key_enc', '')))
        local = (s.cfg.get('ai_url', '') or '').startswith(('http://127.0.0.1', 'http://localhost'))
        s.chat_notice.set_notice('' if (has_key or local) else 'Для ответов ИИ нужен API-ключ. Команды (громкость, заметки, сайты) работают и без него.')

    def set_chat_busy(s, busy):
        s.ai_busy = busy
        s.composer.set_busy(busy)

    def _ensure_conv(s):
        if s.chat_conv is None:
            s.chat_conv = s.chats.new_conv()

    def _record(s, role, content, attach=None, ok=True):
        s._ensure_conv()
        s.chats.add(s.chat_conv, role, content, attach)
        m = {'role': role, 'content': content}
        if attach:
            m['attach'] = attach
        if role == 'action':
            m['ok'] = ok
        s.chat_msgs.append(m)
        return m

    # ==================== ОТПРАВКА ====================
    def send_chat(s):
        s.submit_chat()

    def stop_btn(s):
        s.stop_chat()

    def chat_suggest(s, text, run):
        if run:
            s.submit_chat(text)
        else:
            s.composer.set_text(text)
            s.composer.focus()

    def submit_chat(s, text=None, voice=False):
        """Единая точка: поле ввода, голос, подсказки, командная строка. Команда → выполняется на месте, остальное → ИИ."""
        if s.ai_busy and text is None:
            s.stop_chat()
            return
        from_field = text is None
        q = (s.composer.text() if from_field else text).strip()
        atts = list(s.chat_att)
        if not q and not atts:
            return
        cmd = parse(q) if (q and not atts) else None
        if cmd and cmd.action in ('ask_screen', 'ask_clip', 'ask_ocr'):
            if from_field:
                s.composer.clear()
            q = cmd.args.get('q', q)
            if cmd.action == 'ask_screen':
                s.attach_screen()
            elif cmd.action == 'ask_clip':
                if not s.attach_clipboard():
                    return
            else:
                s._pending_q = q
                s.attach_ocr_screen()
                return
            s.submit_chat(q)
            return
        if from_field:
            s.composer.clear()
        if s.ai_busy:
            s.stop_chat()
        if voice and s.stack.currentIndex() != CHAT_TAB:
            s.go_tab('chat')
        if cmd:
            s.run_local(q, cmd)
        else:
            s.send_to_ai(q, atts)

    def run_local(s, q, cmd):
        silent = cmd.action in ('new_chat', 'island_close')
        if not silent:
            s._record('user', q, [{'kind': 'cmd'}])
            s.chat_view.add('user', q)
        ok, text = s.exec_command(cmd)
        if silent:
            return
        text = text or cmd.label
        if text:
            s._record('action', text, ok=ok)
            s.chat_view.add('action', text, ok)
        s.chat_header_refresh()

    def send_to_ai(s, q, atts):
        content = q or default_prompt(atts)
        s._last_sent = (q, atts)
        attach = [{k: v for k, v in a.items() if k != 'tip'} for a in atts]
        s._record('user', content, attach or None)
        s.chat_view.add('user', content, attach)
        s._ai_bubble = s.chat_view.add('assistant', '')
        s._ai_bubble.set_thinking(True)
        s.att_clear()
        s.ai_partial = []
        s.ai_token += 1
        s.ai_cancel = threading.Event()
        s.set_chat_busy(True)
        s.chat_header_refresh()
        system = s.cfg.get('ai_system', DEFAULT_SYSTEM)
        if has_context(s.chat_msgs):
            system = f"{system}\n\n{CONTEXT_NOTE}"
        threading.Thread(target=s._ai_stream, args=(s.ai_token, list(s.chat_msgs), s.ai_cancel, s.ai_client(), system,
                                                     int(s.cfg.get('ai_ctx_chars', 24000))), daemon=True).start()

    def _ai_stream(s, token, msgs, cancel, client, system, max_chars):
        """Рабочий поток: только сеть, файлы и сигналы, к виджетам Qt не прикасается."""
        buf, last, err = [], time.monotonic(), ''
        try:
            history = build_model_history(msgs)
            for piece in client.stream(history, system, max_chars, cancel):
                buf.append(piece)
                if time.monotonic() - last > 0.05:
                    s.aiDeltaSignal.emit(token, ''.join(buf))
                    buf, last = [], time.monotonic()
        except Exception as e:
            err = str(e) or type(e).__name__
        if buf:
            s.aiDeltaSignal.emit(token, ''.join(buf))
        s.aiDoneSignal.emit(token, err)

    def on_ai_delta(s, token, text):
        if token != s.ai_token or s._ai_bubble is None:
            return
        s.ai_partial.append(text)
        if s._ai_bubble.thinking:
            s._ai_bubble.set_thinking(False)
        s._ai_bubble.set_text(''.join(s.ai_partial))

    def on_ai_done(s, token, err):
        if token != s.ai_token:
            return
        s.set_chat_busy(False)
        answer = ''.join(s.ai_partial)
        bubble = s._ai_bubble
        s.ai_partial, s._ai_bubble = [], None
        if answer:
            s._record('assistant', answer)
            if bubble is not None:
                bubble.set_thinking(False)
                bubble.set_text(answer)
            if err:
                s.chat_view.add('error', f"Ошибка: {err}")
            return
        if err and s.chat_msgs and s.chat_msgs[-1]['role'] == 'user':
            s.chat_msgs.pop()                        # неудачный вопрос не засоряет историю — возвращаем в поле ввода
            s.chats.pop_last(s.chat_conv, 'user')
            q, atts = s._last_sent or ('', [])
            s.composer.set_text(q)
            s.chat_att = list(atts)
            s.composer.set_attachments(s.chat_att)
        s.render_chat()
        if err:
            s.chat_view.add('error', f"Ошибка: {err}")
        s.chat_view.to_bottom()

    def stop_chat(s):
        if s.ai_cancel is not None:
            s.ai_cancel.set()

    def new_chat(s):
        s.stop_chat()
        s.ai_token += 1                                 # запоздавшие фрагменты старого ответа будут проигнорированы
        s.set_chat_busy(False)
        s.chat_conv, s.chat_msgs, s.ai_partial = None, [], []
        s.att_clear()
        s.render_chat()

    def load_chat(s, conv_id):
        s.stop_chat()
        s.ai_token += 1
        s.set_chat_busy(False)
        s.chat_conv, s.chat_msgs = conv_id, s.chats.messages(conv_id)
        s.render_chat()

    def chat_history_menu(s):
        m = s.mk_menu()
        convs = s.chats.convs()
        if not convs:
            m.addAction('История пуста').setEnabled(False)
        for c in convs:
            title = (c['title'] or 'Без названия')[:44]
            a = m.addAction(('● ' if c['id'] == s.chat_conv else '') + title)
            a.triggered.connect(lambda _=False, i=c['id']: s.load_chat(i))
        if s.chat_conv is not None:
            m.addSeparator()
            m.addAction('Удалить этот диалог').triggered.connect(lambda: (s.chats.delete_conv(s.chat_conv), s.new_chat()))
        m.exec(QCursor.pos())

    # ---------- действия над сообщениями ----------
    def chat_link(s, url):
        if url.lower().startswith(('http://', 'https://')):
            safe_open_path(url)

    def chat_copy(s, text):
        QGuiApplication.clipboard().setText(text)
        s.chat_toast('Скопировано', text[:50].replace('\n', ' '), QColor('#34c759'), 2.0)

    def chat_open_image(s, path):
        pm = QPixmap(path)
        if not pm.isNull():
            ImageViewer(pm, 'Вложение чата', path)

    def chat_restyle(s):
        if hasattr(s, 'chat_view'):
            s.chat_view.restyle()
            s.chat_toast_w.update()

    # ==================== КОМАНДНАЯ СТРОКА ====================
    def open_command_palette(s):
        cmd, ok = QInputDialog.getText(None, 'Командная строка Island',
                                       'Команда (wifi, bluetooth, тема, блок, таймер 10, 245*18 или вопрос ИИ):')
        if not ok or not cmd.strip():
            return
        q = cmd.strip().lower()
        if q == 'wifi':
            subprocess.Popen(['explorer.exe', 'ms-settings:network-wifi'])
        elif q == 'bluetooth':
            subprocess.Popen(['explorer.exe', 'ms-settings:bluetooth'])
        elif q in ('тема', 'theme'):
            s.toggle_win_theme()
        elif q in ('блок', 'заблокировать', 'lock'):
            ctypes.windll.user32.LockWorkStation()
        elif q.startswith('таймер') and not re.search(r'[a-zа-я]\s*\d+\s*(?:час|ч\b|сек|с\b)', q):
            m = re.search(r'(\d+)', q)
            mins = min(int(m.group(1)), 1440) if m else 10
            s.set_timer_sec(mins * 60)
            s.trun = True
            s.pop('Таймер запущен', f'На {mins} мин.', (QColor('#ff9f0a'), 'notes'))
        elif re.match(r'^[\d\s\+\-\*\/\(\)\.\%]+$', q):
            try:
                res = safe_math_eval(q)
                QGuiApplication.clipboard().setText(res)
                s.pop(f"= {res}", 'Результат скопирован в буфер', (QColor('#34c759'), 'cmd'))
            except Exception:
                s.pop('Ошибка расчёта', 'Недопустимое математическое выражение', (QColor('#ff453a'), 'cmd'))
        else:
            s.go_tab('chat')                          # остальное — как в чате: команды ассистента или вопрос ИИ
            s.submit_chat(cmd.strip())
