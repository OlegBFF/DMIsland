"""Конфигурация: значения по умолчанию, загрузка и атомарное сохранение, группы ключей настроек."""
import json
import os
from pathlib import Path
from core.constants import CFG_PATH
from core.security import dpapi_encrypt
from core.utils import log


DEFAULT_CFG = {
    'city': 'Москва',
    'lang': 'ru',
    'theme': 'obsidian',              # ключ из THEMES или system
    'accent_mode': 'theme',           # theme | cover | custom
    'accent_custom': '#ff4d6d',
    'anim_style': 'liquid',           # liquid | smooth | snappy
    'glow': True,                     # свечение острова (для тем с glow)
    'window_fit': 'smart_dodge',      # smart_dodge | titlebar_snap | workarea | normal
    'scale': 1.0,                     # устарело (оставлено для совместимости), см. ui_scale
    'ui_scale': 'auto',               # auto | 0.9 | 1.0 | 1.15 | 1.3 | 1.5 — масштаб всего интерфейса (после перезапуска)
    'open_delay': 0.12,               # секунд удержания курсора у верхней грани до раскрытия (защита от случайных касаний)
    'hide_apps': '',                  # процессы через запятую (vlc.exe, mpv.exe): при их фокусе остров прячется
    'auto_peek': True,                # в развёрнутых окнах остров через паузу сжимается в тонкую линию
    'peek_after': 4.0,
    'notif_enabled': True,
    'notif_normal': 'toast',          # card | toast | silent
    'notif_system': 'toast',          # card | toast | silent
    'notif_important_secs': 15,       # сколько важное сообщение остаётся на экране (наведение продлевает)
    'notif_dnd': False,               # «Не беспокоить»
    'notif_dnd_important': True,      # пропускать важные в режиме «Не беспокоить» и в тихие часы
    'notif_quiet_from': '',           # тихие часы, например 23:00
    'notif_quiet_to': '',             # … до 08:00
    'notif_important_apps': '',       # свои важные приложения через запятую
    'notif_muted_apps': '',           # приложения, уведомления которых не показываются
    'notif_keywords': '',             # слова, делающие уведомление важным
    'notif_keep_days': 30,
    'notif_clear_windows': False,     # убирать из центра Windows то, что закрыли в острове
    'notif_autopaste': False,         # после «Ответить» вставлять ответ в открытое приложение (Ctrl+V)
    'opacity_idle': 0.96,
    'opacity_open': 0.98,
    'monitor': 0,
    'offset_x': 0,
    'show_in_capture': False,
    'click_through': False,
    'autostart': False,
    'game_mode': 'hide',              # hide | off — прятать остров при полноэкранных окнах
    'device_events': True,            # USB / зарядка / наушники
    'privacy_dots': True,             # индикаторы микрофона и камеры
    'player_auto': True,              # автоматически выбирать играющий плеер
    'player_ignore': '',              # игнорируемые плееры через запятую
    'pill_music': 'normal',           # normal | wide | mini
    'lyrics_enabled': True,
    'edge_eq': True,
    'character': 'none',              # none | astro | cat | pixel | eyes | fire
    'fps': 30,
    'rec_format': 'mp4',
    'rec_audio_system': True,         # писать системный звук (WASAPI loopback)
    'rec_audio_mic': False,           # писать микрофон
    'rec_max_min': 30,                # автоостановка записи, минут
    'rec_gif_sec': 20,                # максимум секунд для GIF
    'rec_gif_mem_mb': 64,             # лимит памяти GIF без ffmpeg
    'clip_max_items': 300,
    'clip_keep_days': 30,
    'clip_secret_policy': 'mask',     # mask — хранить зашифрованно и скрывать, skip — не хранить
    'clip_secret_ttl': 120,           # секунд жизни секретных записей
    'clip_secret_heuristic': True,    # считать секретом похожие на пароль строки
    'upload_service': 'none',
    'upload_key_enc': '',             # Зашифровано через Windows DPAPI
    'ai_url': 'https://api.openai.com/v1/chat/completions',
    'ai_key_enc': '',                 # Зашифровано через Windows DPAPI
    'ai_model': 'gpt-4o-mini',
    'ai_system': 'Ты — полезный ассистент. Отвечай по существу и на языке пользователя.',
    'ai_ctx_chars': 24000,            # бюджет истории диалога (символов), старые сообщения отбрасываются
    'chat_keep_open': True,            # в чате остров не сворачивается от клика вне острова (закрыть: ▾, Esc, «закрой остров»)
    'voice_lang': 'ru-RU',            # язык распознавания голоса
    'ai_ctx_notice': False,           # показано ли предупреждение «контекст уйдёт на ИИ-сервер»
    'notif_group': True,              # история уведомлений сгруппирована по приложениям
    'notif_auto_links': False,        # сами загружать картинки по ссылкам из уведомлений (иначе — по кнопке: загрузка выдаёт отправителю, что вы прочитали)
    'apps': [],
    'notes': [{'title': 'Заметка', 'html': ''}, {'title': 'Идеи', 'html': ''}],
    'color_history': ['#FF4D6D', '#4DA3FF', '#34C759', '#FF9F0A']
}


# ==================== УТИЛИТЫ И ТЕМЫ ====================
def load_cfg():
    c = dict(DEFAULT_CFG)
    try:
        if CFG_PATH.exists():
            loaded = json.loads(CFG_PATH.read_text('utf-8'))
            # Миграция открытых ключей в защищённое хранилище DPAPI
            for plain_k, enc_k in (('ai_key', 'ai_key_enc'), ('upload_key', 'upload_key_enc')):
                if loaded.get(plain_k):
                    loaded[enc_k] = dpapi_encrypt(loaded.pop(plain_k))
            if isinstance(loaded.get('apps'), list) and loaded['apps'] and isinstance(loaded['apps'][0], str):
                loaded['apps'] = [{'type': 'app', 'name': Path(p).stem, 'path': p} for p in loaded['apps']]
            c.update(loaded)
    except Exception:
        pass
    return c

_LAST_CFG = [None]


def save_cfg(c):
    """Атомарная запись (tmp → replace), без лишних перезаписей одинакового содержимого."""
    try:
        CFG_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Удаляем любые временные открытые ключи перед записью на диск
        clean = {k: v for k, v in c.items() if k not in ('ai_key', 'upload_key')}
        data = json.dumps(clean, ensure_ascii=False, indent=2)
        if data == _LAST_CFG[0]:
            return
        tmp = CFG_PATH.with_suffix('.tmp')
        tmp.write_text(data, 'utf-8')
        os.replace(tmp, CFG_PATH)
        _LAST_CFG[0] = data
    except Exception as ex:
        log(f"save_cfg: {ex!r}")

# ==================== ОКНО НАСТРОЕК ====================
STYLE_KEYS = {'theme', 'accent_mode', 'accent_custom'}

WINDOW_KEYS = {'window_fit', 'click_through', 'show_in_capture'}   # требуют apply_window_integration()

PLACE_KEYS = {'scale', 'offset_x', 'monitor'}                    # достаточно переставить окно
