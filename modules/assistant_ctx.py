"""Контекст Windows для ИИ: скриншот экрана/области, текст с экрана (OCR), буфер обмена, голосовой ввод."""
import threading
from datetime import datetime
from PySide6.QtCore import QBuffer, QIODevice, QTimer
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QImage, QPixmap
from core.constants import DATA_DIR
from core.secrets_detect import classify
from core.utils import log
from modules.capture import ocr_png_bytes
from modules.voice import VoiceError, listen_and_recognize
from ui.overlays import SnapOverlay

CHAT_IMG_DIR = DATA_DIR / 'chat_images'
MAX_SIDE, MAX_CTX_TEXT, MAX_ATT = 1600, 8000, 3
DEFAULT_PROMPTS = {
    'shot': 'Опиши, что на скриншоте, и подскажи, что с этим можно сделать.',
    'img': 'Опиши, что на изображении.',
    'ocr': 'Объясни, что написано в этом тексте с экрана, и выдели главное.',
    'clip': 'Объясни, что в буфере обмена, и что с этим можно сделать.',
}


def default_prompt(atts) -> str:
    kinds = [a['kind'] for a in atts]
    for k in ('shot', 'img', 'ocr', 'clip'):
        if k in kinds:
            return DEFAULT_PROMPTS[k]
    return ''


def save_ctx_image(img: QImage):
    """Уменьшенная JPEG-копия для ИИ (≤1600 px по длинной стороне). Старые файлы чистятся (храним 40 последних)."""
    CHAT_IMG_DIR.mkdir(parents=True, exist_ok=True)
    if max(img.width(), img.height()) > MAX_SIDE:
        from PySide6.QtCore import Qt
        img = img.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    fp = CHAT_IMG_DIR / f"{datetime.now():%Y%m%d_%H%M%S_%f}.jpg"
    img.convertToFormat(QImage.Format_RGB32).save(str(fp), 'JPG', 82)
    try:
        old = sorted(CHAT_IMG_DIR.glob('*.jpg'), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in old[40:]:
            f.unlink(missing_ok=True)
    except OSError:
        pass
    return str(fp)


class AssistantCtxMixin:
    """Часть класса Island: вложения чата и голос."""

    def init_ctx(s):
        s.chat_att, s._pending_q, s._voice_cancel, s._voice_bar = [], None, threading.Event(), False

    # ---------- вложения ----------
    def _ai_host(s) -> str:
        from urllib.parse import urlparse
        return urlparse(s.cfg.get('ai_url', '')).hostname or 'ИИ-сервер'

    def _ctx_notice(s):
        if not s.cfg.get('ai_ctx_notice'):
            s.cfg['ai_ctx_notice'] = True
            from core.config import save_cfg
            save_cfg(s.cfg)
            s.chat_toast('Контекст уйдёт на ИИ-сервер', f'{s._ai_host()} · убрать вложение можно крестиком', QColor('#ff9f0a'), 5.0)

    def att_add(s, att):
        s.chat_att = [a for a in s.chat_att if not (a['kind'] == att['kind'] and a['kind'] in ('shot', 'img', 'ocr', 'clip'))][-(MAX_ATT - 1):] + [att]
        s.composer.set_attachments(s.chat_att)
        s._ctx_notice()
        s.composer.focus()

    def att_remove(s, idx):
        if 0 <= idx < len(s.chat_att):
            s.chat_att.pop(idx)
            s.composer.set_attachments(s.chat_att)

    def att_clear(s):
        s.chat_att = []
        s.composer.set_attachments([])

    def chat_attach_menu(s):
        m = s.mk_menu()
        m.addAction('Скриншот экрана').triggered.connect(s.attach_screen)
        m.addAction('Область экрана…').triggered.connect(lambda: s.pick_area('ctx_shot'))
        m.addSeparator()
        m.addAction('Текст с экрана (OCR)').triggered.connect(s.attach_ocr_screen)
        m.addAction('Текст из области…').triggered.connect(lambda: s.pick_area('ctx_ocr'))
        m.addSeparator()
        m.addAction('Буфер обмена').triggered.connect(s.attach_clipboard)
        if s.chat_att:
            m.addSeparator()
            m.addAction('Убрать все вложения').triggered.connect(s.att_clear)
        m.exec(QCursor.pos())

    def attach_screen(s):
        pm = s.grab()
        s.att_add({'kind': 'shot', 'label': 'Скриншот экрана', 'path': save_ctx_image(pm.toImage()),
                   'tip': f'Уйдёт на {s._ai_host()}'})

    def pick_area(s, mode):
        QTimer.singleShot(110, lambda: setattr(s, 'ov', SnapOverlay(s.grab(), mode, s)))

    def on_ctx_crop(s, mode, pm: QPixmap):
        if pm.isNull():
            return
        if mode == 'ctx_shot':
            s.att_add({'kind': 'shot', 'label': 'Область экрана', 'path': save_ctx_image(pm.toImage()),
                       'tip': f'Уйдёт на {s._ai_host()}'})
        else:
            s._ocr_async(pm, 'Текст области')

    def attach_ocr_screen(s):
        s._ocr_async(s.grab(), 'Текст с экрана')

    def _ocr_async(s, pm: QPixmap, label):
        ba = QBuffer()
        ba.open(QIODevice.WriteOnly)
        pm.save(ba, 'PNG')
        png = bytes(ba.data())
        s.chat_toast('Распознаю текст…', 'Windows OCR', QColor('#0a84ff'), 2.5)

        def run():
            try:
                txt = ocr_png_bytes(png)
                s.ctxOcrSignal.emit(label, txt, '')
            except Exception as ex:
                log(f'chat ocr: {ex!r}')
                s.ctxOcrSignal.emit(label, '', 'Установите winrt-Windows.Media.Ocr')
        threading.Thread(target=run, daemon=True).start()

    def on_ctx_ocr(s, label, text, err):
        if err or not text:
            s.chat_toast('Текст не найден', err or 'Попробуйте выбрать область крупнее', QColor('#ff9f0a'), 3.5)
            s._pending_q = None
            return
        s.att_add({'kind': 'ocr', 'label': f'{label} · {len(text)} симв.', 'text': text[:MAX_CTX_TEXT], 'tip': text[:200]})
        if s._pending_q is not None:                      # «прочитай текст с экрана и объясни» — сразу отправляем
            q, s._pending_q = s._pending_q, None
            s.submit_chat(q)

    def attach_clipboard(s) -> bool:
        md = QGuiApplication.clipboard().mimeData()
        if md is None:
            return False
        if md.hasImage():
            img = QGuiApplication.clipboard().image()
            if not img.isNull():
                s.att_add({'kind': 'img', 'label': 'Изображение из буфера', 'path': save_ctx_image(img), 'tip': f'Уйдёт на {s._ai_host()}'})
                return True
        text = md.text() if md.hasText() else ''
        if not text and md.hasUrls():
            text = '\n'.join(u.toLocalFile() or u.toString() for u in md.urls())
        if not text.strip():
            s.chat_toast('Буфер пуст', 'Скопируйте текст или картинку', QColor('#ff9f0a'), 3.0)
            return False
        secret = classify(text)
        if secret:
            s.chat_toast('Не отправляю буфер', f'Похоже на секрет: {secret}', QColor('#ff453a'), 4.5)
            return False
        s.att_add({'kind': 'clip', 'label': f'Буфер · {len(text)} симв.', 'text': text[:MAX_CTX_TEXT], 'tip': text[:200]})
        return True

    # ---------- голос ----------
    def toggle_voice(s):
        s.chat_voice(from_bar=True)

    def chat_voice(s, from_bar=False):
        if s.voice_listening:
            s._voice_cancel.set()                         # повторный клик — отмена
            return
        s.voice_listening, s._voice_bar = True, from_bar
        s._voice_cancel = cancel = threading.Event()
        if from_bar and s.stack.currentIndex() != 4:
            s.go_tab('chat')
        s.composer.set_listening(True)
        lang = s.cfg.get('voice_lang', 'ru-RU')

        def run():
            try:
                s.voiceSignal.emit('text', listen_and_recognize(cancel, lang))
            except VoiceError as e:
                s.voiceSignal.emit('error', str(e))
            except Exception as e:
                log(f'voice: {e!r}')
                s.voiceSignal.emit('error', 'Голосовой ввод недоступен')
        threading.Thread(target=run, daemon=True).start()

    def on_voice(s, kind, payload):
        s.voice_listening = False
        s.composer.set_listening(False)
        if kind == 'error':
            if payload != 'Отменено':
                s.chat_toast('Голос', payload, QColor('#ff453a'), 3.5)
            return
        if payload:
            s.submit_chat(payload, voice=True)
