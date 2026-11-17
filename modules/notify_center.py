"""Центр уведомлений: приём из Windows, приоритеты, расширяющийся остров, быстрый ответ, отложить, история."""
import time
from datetime import datetime
from PySide6.QtCore import QTimer, Qt
import threading
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPen, QPixmap
from PySide6.QtWidgets import QInputDialog
from core.notif_extract import actions_for, find_image_refs, find_urls
from core.notif_media import fetch_image_bytes, read_local_image
from core.security import safe_open_path
from ui.image_viewer import ImageViewer
from core.notif_rules import PRIORITY_NAMES, classify, is_muted, policy, snooze_options, split_list
from core.stores import NotificationStore
from core.security import dpapi_decrypt
from core.utils import log
from core.win32 import send_ctrl_v
from modules.notify_reply import OpenAndCopyProvider, ReplyRegistry, open_app
from modules.winnotify import WinNotificationListener
from ui.notif_card import CARD_W, PRIO_COL, NotifCard, clamp01

NOTIF_TAB = 8          # индекс вкладки «Уведомления»
MAX_QUEUE = 6


class NotifyMixin:
    """Часть класса Island: NotifyMixin."""

    def init_notify(s):
        s.notifs = NotificationStore(s.db)
        s.replies = ReplyRegistry([OpenAndCopyProvider(s._copy_text, send_ctrl_v, lambda: bool(s.cfg.get('notif_autopaste')))])
        s.nq, s.ncur, s.nicons = [], 0, {}
        s.notif_total, s.nstatus, s._backlog = 6.0, 'init', []
        s._nf_sig, s._notif_prune_t = None, 0.0
        s.card = NotifCard(s)
        s.card.icons = s.nicons
        s.card.reply_info = s._reply_hint
        s.card.replied.connect(s._card_replied)
        s.card.snoozeRequested.connect(s.notif_snooze_menu)
        s.card.openRequested.connect(s.notif_open)
        s.card.dismissed.connect(lambda n: s._remove_from_queue(n['id']))
        s.card.readRequested.connect(s.notif_read)
        s.card.smart_actions = s._smart_actions
        s.card.playing = lambda: s.playing
        s.card.actionRequested.connect(s.notif_action)
        s.card.draftRequested.connect(s.notif_draft)
        s.card.imageRequested.connect(s.notif_view_image)
        s.notifImgSignal.connect(s.on_notif_image)
        s._full_images, s._draft_nid = {}, None
        s.card.navigated.connect(s._card_nav)
        s.card.historyRequested.connect(s.open_notifications_tab)
        s.listener = WinNotificationListener()
        s.listener.received.connect(s.on_win_notification)
        s.listener.status.connect(s.on_notif_status)
        if s.cfg.get('notif_enabled', True):
            s.listener.start()

    def _copy_text(s, text):
        QGuiApplication.clipboard().setText(text)

    def _reply_hint(s, n):
        p = s.replies.find(n)
        return p.placeholder if p else None

    def on_notif_status(s, state):
        s.nstatus = state
        if hasattr(s, 'nf_hint'):
            s.refresh_notifs()

    # ==================== ПРИЁМ ====================
    def on_win_notification(s, d):
        """Главный поток: уведомление пришло из Windows."""
        if not s.cfg.get('notif_enabled', True):
            return
        app, app_id = d.get('app') or '', d.get('app_id') or ''
        if d.get('icon') and app_id not in s.nicons:
            pm = QPixmap()
            if pm.loadFromData(d['icon']):
                s.nicons[app_id] = pm
        if is_muted(app, app_id, s.cfg.get('notif_muted_apps', '')):
            return
        prio = classify(app, app_id, d.get('title', ''), d.get('body', ''), s.cfg.get('notif_important_apps', ''), s.cfg.get('notif_keywords', ''))
        nid, new = s.notifs.add('windows', app_id, app, d.get('title', ''), d.get('body', ''), prio, time.time(), d.get('win_id'))
        s.update_notif_badges()
        if new:
            s.present_notification(s.notifs.get(nid))

    def record_system(s, title, text):
        """События самого острова (флешка, зарядка, микрофон…) попадают в историю как системные — сразу прочитанными."""
        try:
            nid, _ = s.notifs.add('island', 'island', 'Island', title, text, 'system')
            s.notifs.mark_read(nid)
            s.refresh_notifs()
        except Exception as ex:
            log(f"record_system: {ex!r}")

    def present_notification(s, n):
        pol = policy(n['priority'], s.cfg, datetime.now(), fullscreen=s.fs or s.app_hidden, recording=s.recorder.recording)
        if pol['show'] == 'silent':
            if pol['reason'] == 'fullscreen':
                s._backlog.append(n['id'])                   # покажем сводкой, когда выйдете из полного экрана
            return
        if s.mode == 'open':
            if s.chat_hold() and pol['show'] != 'silent':    # в чате остров не сворачивается — коротко показываем внутри чата
                body = (n['body'] or '').replace('\n', ' ')
                s.chat_toast(n['title'] or n['app'], f"{n['app']} · {body}"[:80], PRIO_COL[n['priority']], 4.0, 'bell')
            return                                           # человек работает с панелью — только бейдж на вкладке
        if pol['show'] == 'toast' and s.mode != 'notif':
            icon = s.nicons.get(n['app_id']) or (PRIO_COL[n['priority']], 'chat' if n['priority'] != 'system' else 'info')
            body = (n['body'] or '').replace('\n', ' ')
            s.pop(n['title'] or n['app'], f"{n['app']} · {body}"[:90], icon, pol['secs'])
            return
        s.show_card(n, pol)

    # ==================== КАРТОЧКА ====================
    def notif_h(s) -> int:
        return min(int(s.card.preferred_height()) + 26, 420)

    def show_card(s, n, pol):
        now = time.time()
        ids = [x['id'] for x in s.nq]
        if n['id'] in ids:
            s.nq[ids.index(n['id'])] = n
        else:
            key = (n.get('app_id') or n.get('app') or '').casefold()
            same = [i for i, x in enumerate(s.nq) if (x.get('app_id') or x.get('app') or '').casefold() == key]
            if same:
                s.nq.insert(same[-1] + 1, n)                  # сообщения одного приложения стоят рядом (группа)
                s.nq = s.nq[-MAX_QUEUE:]
            else:
                s.nq = (s.nq + [n])[-MAX_QUEUE:]
        if s.mode != 'notif':
            s.mode, s.leave, s.until, s.notif_total = 'notif', 0, now + pol['secs'], max(pol['secs'], 1.0)
        else:
            s.until = max(s.until, now + pol['secs'])
            s.notif_total = max(s.notif_total, s.until - now)
        s.ncur = next((i for i, x in enumerate(s.nq) if x['id'] == n['id']), len(s.nq) - 1)
        s.card.set_items(s.nq, s.ncur)
        s._load_previews(n, bool(s.cfg.get('notif_auto_links')))
        s.anim_timer.setInterval(s.frame_ms_v)

    def close_card(s, clear=False):
        s.card.cancel_reply(silent=True)
        s.set_typing(False)
        if s.mode == 'notif':
            s.mode = 'idle'
        if clear:
            s.nq = []
            s.card.hide()
            s.card.previews.clear()                          # превью живут, пока жива карточка
            s._full_images.clear()

    def _remove_from_queue(s, nid):
        s.nq = [x for x in s.nq if x['id'] != nid]
        if not s.nq:
            s.close_card()
            return
        s.ncur = min(s.ncur, len(s.nq) - 1)
        s.card.set_items(s.nq, s.ncur)
        s.until = max(s.until, time.time() + 3.0)

    def _card_nav(s, d):
        if s.nq:
            s.ncur = (s.ncur + d) % len(s.nq)
            s.card.set_items(s.nq, s.ncur)
            s.until = max(s.until, time.time() + 4.0)

    # ==================== ДЕЙСТВИЯ ИЗ СОДЕРЖИМОГО ====================
    def _smart_actions(s, n):
        """Кнопки карточки: ссылки, код подтверждения, номер, управление музыкой, «показать картинку».
        Windows не отдаёт кнопки и вложения чужого тоста — всё строится из текста сообщения."""
        acts = actions_for(n, False, s.mapp if s.playing else '')
        if n['id'] not in s.card.previews and not s.cfg.get('notif_auto_links'):
            refs = [r for r in find_image_refs(f"{n.get('title') or ''}\n{n.get('body') or ''}") if r[0] == 'url']
            if refs:
                acts.append({'key': 'preview_url', 'label': 'Показать картинку', 'arg': refs[0][1]})
        return acts

    def _load_previews(s, n, allow_urls: bool):
        """Рабочий поток: картинки из локальных путей (всегда) и по ссылкам (если разрешено) → превью в карточке."""
        refs = find_image_refs(f"{n.get('title') or ''}\n{n.get('body') or ''}")
        if not allow_urls:
            refs = [r for r in refs if r[0] == 'file']
        if not refs:
            return
        nid = n['id']

        def run():
            for kind, ref in refs[:3]:
                try:
                    data = fetch_image_bytes(ref) if kind == 'url' else read_local_image(ref)
                    img = QImage.fromData(data)
                    if not img.isNull():
                        s.notifImgSignal.emit(nid, img)
                except Exception as ex:
                    log(f"notif preview: {ex!r}")
        threading.Thread(target=run, daemon=True).start()

    def on_notif_image(s, nid, img):
        pm = QPixmap.fromImage(img.scaled(480, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation) if max(img.width(), img.height()) > 480 else img)
        lst = s.card.previews.setdefault(nid, [])
        if len(lst) < 3:
            lst.append(pm)
            s._full_images.setdefault(nid, []).append(img)
        if s.nq and any(x['id'] == nid for x in s.nq):
            s.until = max(s.until, time.time() + 6.0)
        s.card.update()

    def notif_view_image(s, n, i):
        imgs = s._full_images.get(n['id'], [])
        if 0 <= i < len(imgs):
            ImageViewer(QPixmap.fromImage(imgs[i]), f"{n.get('app') or ''} · {n.get('title') or ''}")

    def notif_action(s, n, key, arg):
        if key == 'link':
            ok = safe_open_path(arg)
            s.notifs.mark_read(n['id'])
            s.close_card(clear=True)
            s._after_change()
            if not ok:
                s.pop('Ссылка не открылась', arg[:50], (QColor('#ff9f0a'), 'info'), 3.0)
        elif key in ('copy_code', 'copy_phone'):
            s._copy_text(arg)
            s.pop('Скопировано', arg, (QColor('#34c759'), 'check'), 2.4)
        elif key == 'music':
            s.media.cmd({'prev': 'try_skip_previous_async', 'next': 'try_skip_next_async'}.get(arg, 'try_toggle_play_pause_async'))
            s.until = max(s.until, time.time() + 4.0)
        elif key == 'preview_url':
            s._load_previews({**n, 'title': '', 'body': arg}, True)
            s.until = max(s.until, time.time() + 6.0)

    def notif_draft(s, n):
        """ИИ предлагает короткий ответ на сообщение (текст уходит на ИИ-сервер только по этой кнопке)."""
        if not dpapi_decrypt(s.cfg.get('ai_key_enc', '')) and not (s.cfg.get('ai_url', '') or '').startswith(('http://127.0.0.1', 'http://localhost')):
            s.card.set_draft('')
            s.pop('Нужен API-ключ ИИ', 'Настройки → ИИ и ссылки', (QColor('#ff9f0a'), 'info'), 3.5)
            return
        s._draft_nid = n['id']
        client = s.ai_client()
        prompt = (f"Сообщение от «{n.get('title') or n.get('app')}» ({n.get('app')}):\n{n.get('body') or n.get('title')}\n\n"
                  "Предложи один короткий естественный ответ на него на языке сообщения. Только текст ответа, без кавычек и пояснений.")

        def run():
            try:
                ans = client.complete([{'role': 'user', 'content': prompt}], system='', max_chars=4000).strip().strip('"«»')
                s.aiReplySignal.emit(f"DRAFT:{n['id']}:{ans}")
            except Exception as e:
                s.aiReplySignal.emit(f"DRAFTERR:{e}")
        threading.Thread(target=run, daemon=True).start()

    # ==================== ДЕЙСТВИЯ ====================
    def _after_change(s):
        s.update_notif_badges()
        s.refresh_notifs()

    def notif_read(s, n):
        s.notifs.mark_read(n['id'])
        if s.cfg.get('notif_clear_windows') and n.get('win_id') is not None:
            s.listener.remove(n['win_id'])
        s._remove_from_queue(n['id'])
        s._after_change()

    def notif_open(s, n):
        ok = open_app(n.get('app_id', ''))
        s.notifs.mark_read(n['id'])
        s.close_card(clear=True)
        s._after_change()
        if not ok:
            s.pop('Не удалось открыть', n.get('app') or 'Приложение', (QColor('#ff9f0a'), 'info'), 3.0)

    def notif_snooze_menu(s, n):
        m = s.mk_menu()
        for label, when in snooze_options(datetime.now()):
            m.addAction(label).triggered.connect(lambda _=False, w=when: s.notif_snooze(n, w))
        m.exec(QCursor.pos())

    def notif_snooze(s, n, when):
        s.notifs.snooze(n['id'], when.timestamp())
        if s.mode == 'notif':
            s._remove_from_queue(n['id'])
        s._after_change()

    def _card_replied(s, n, text):
        ok, msg = s.replies.reply(n, text)
        if ok:
            s.notifs.mark_read(n['id'])
        s.close_card(clear=True)
        s._after_change()
        s.pop('Ответ' if ok else 'Ответ не отправлен', msg, (QColor('#34c759'), 'check') if ok else (QColor('#ff453a'), 'close'), 4.5)

    def notif_reply_dialog(s, n):
        """Ответ из истории (в карточке поле ввода встроено)."""
        text, ok = QInputDialog.getText(None, 'Ответить', f"{n.get('app') or ''}: {n.get('title') or ''}")
        if ok and text.strip():
            done, msg = s.replies.reply(n, text)
            if done:
                s.notifs.mark_read(n['id'])
            s._after_change()
            s.pop('Ответ' if done else 'Ответ не отправлен', msg, (QColor('#34c759'), 'check') if done else (QColor('#ff453a'), 'close'), 4.5)

    def open_notifications_tab(s):
        s.close_card(clear=True)
        s.tabs.idx = NOTIF_TAB
        s.switch(NOTIF_TAB)
        s.mode, s.leave = 'open', 0
        s.tabs.update()
        s.refresh_notifs()

    def toggle_dnd(s):
        s.set_cfg('notif_dnd', not s.cfg.get('notif_dnd', False))
        s.refresh_notifs()

    def add_app_rule(s, key, app):
        items = split_list(s.cfg.get(key, ''))
        if app.lower() not in items:
            s.set_cfg(key, ', '.join(items + [app.lower()]))

    # ==================== ТАЙМЕРЫ И СЧЁТЧИКИ ====================
    def update_notif_badges(s):
        c = s.notifs.unread_counts()
        s._notif_unread = c
        total = sum(c.values())
        s.tabs.set_badge(NOTIF_TAB, total, PRIO_COL['important'] if c['important'] else PRIO_COL['system'])
        s.tabs.update()

    def check_notif_timers(s):
        """Раз в секунду: вернуть отложенные, раз в 10 минут чистить старое."""
        try:
            for n in s.notifs.due_snoozed():
                n = s.notifs.get(n['id'])
                s.update_notif_badges()
                s.present_notification(n)
                s.refresh_notifs()
            now = time.monotonic()
            if now - s._notif_prune_t > 600:
                s._notif_prune_t = now
                s.notifs.prune(int(s.cfg.get('notif_keep_days', 30)))
        except Exception as ex:
            log(f"check_notif_timers: {ex!r}")

    def flush_backlog(s):
        """Вышли из полного экрана / вернули остров: сводка за время тишины."""
        if not s._backlog:
            return
        ns = [s.notifs.get(i) for i in s._backlog]
        s._backlog = []
        ns = [n for n in ns if n and not n['read']]
        if not ns:
            return
        imp = sum(1 for n in ns if n['priority'] == 'important')
        s.pop('Пока вы были заняты', f"Новых: {len(ns)}" + (f" · важных: {imp}" if imp else ''),
              (PRIO_COL['important'] if imp else PRIO_COL['system'], 'chat'), 5.0)

    # ==================== ТИК И РИСОВАНИЕ ====================
    def tick_notif(s, now, inx, ly, h):
        busy = s.card.replying or s._typing
        hover = inx and -4 <= ly <= h + 8
        if hover or busy:
            s.until = max(s.until, now + 2.2)
        elif now > s.until:
            s.close_card()
        s.card.progress = 1.0 if (hover or busy) else clamp01((s.until - now) / max(s.notif_total, 0.5))

    def sync_card(s, cx):
        show = bool(s.nq) and (s.mode == 'notif' or (s.mode == 'idle' and s.sh.x > 60))
        if not show:
            if s.nq and s.mode == 'idle':
                s.nq = []
            if s.card.isVisible():
                s.card.hide()
            return
        cw, ch = CARD_W - 36, int(s.card.preferred_height())
        if (s.card.width(), s.card.height()) != (cw, ch):
            s.card.resize(cw, ch)
        s.card.move(int(cx - cw / 2), 12)
        nh = max(s.notif_h(), 80)
        s.card.fade = clamp01((s.sw.x - 0.55 * CARD_W) / (0.4 * CARD_W)) * clamp01((s.sh.x - 0.55 * nh) / (0.4 * nh))
        if not s.card.isVisible():
            s.card.show()
        s.card.update()

    def paint_notif_ring(s, p, cx, w, h, now):
        """Обводка острова цветом приоритета; у важных — пульсирующая."""
        import math
        n = s.nq[s.ncur] if 0 <= s.ncur < len(s.nq) else None
        if not n:
            return
        c = QColor(PRIO_COL.get(n['priority'], PRIO_COL['normal']))
        c.setAlpha(int(110 + 110 * (0.5 + 0.5 * math.sin(now * 3.2))) if n['priority'] == 'important' else 110)
        p.setPen(QPen(c, 1.8))
        p.setBrush(Qt.NoBrush)
        p.drawPath(s.liquid_path(cx, w, h, 0, now))

    def paint_notif_badge(s, p, x0, w, h, now):
        """Индикатор непрочитанных на пилюле: точка приоритета, при нескольких — со счётчиком."""
        import math
        from PySide6.QtCore import QPointF, QRectF
        from ui.widgets import fnt
        c = getattr(s, '_notif_unread', None)
        if not c or not s.cfg.get('notif_badge', True):
            return
        total = sum(c.values())
        if not total:
            return
        col = QColor(PRIO_COL['important'] if c['important'] else PRIO_COL['system'])
        r = 4.2 + (1.2 * (0.5 + 0.5 * math.sin(now * 3.2)) if c['important'] else 0.0)
        ctr = QPointF(x0 + w - 16, h / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        if total > 1:
            p.drawEllipse(ctr, 8.0, 8.0)
            p.setPen(QColor('white'))
            p.setFont(fnt(8, QFont.Bold))
            p.drawText(QRectF(ctr.x() - 8, ctr.y() - 8, 16, 16), Qt.AlignCenter, str(min(total, 99)))
        else:
            p.drawEllipse(ctr, r, r)
