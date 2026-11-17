"""Подготовка истории диалога для модели (без Qt): вложения превращаются в текст и изображения."""
import base64
from pathlib import Path


def image_data_url(path: str):
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    return 'data:image/jpeg;base64,' + base64.b64encode(raw).decode('ascii')


def build_model_history(msgs, load_image=image_data_url):
    """msgs — как в ChatStore.messages(). Строки-результаты команд и сами локальные команды модели не отправляются;
    изображение уходит только из ПОСЛЕДНЕГО сообщения с картинкой (экономия токенов), в старых остаётся пометка."""
    last_img = -1
    for i, m in enumerate(msgs):
        if m['role'] == 'user' and any(a.get('kind') in ('shot', 'img') and a.get('path') for a in m.get('attach') or ()):
            last_img = i
    out = []
    for i, m in enumerate(msgs):
        atts = m.get('attach') or []
        if m['role'] == 'action' or any(a.get('kind') == 'cmd' for a in atts):
            continue
        content, imgs = m['content'], []
        for a in atts:
            k = a.get('kind')
            if k in ('ocr', 'clip') and a.get('text'):
                content += f"\n\n[{'Текст с экрана' if k == 'ocr' else 'Буфер обмена'}]\n```\n{a['text']}\n```"
            elif k in ('shot', 'img'):
                url = load_image(a['path']) if (i == last_img and a.get('path')) else None
                if url:
                    imgs.append(url)
                else:
                    content += '\n\n[ранее был приложен снимок экрана, он больше недоступен]'
        d = {'role': m['role'], 'content': content}
        if imgs:
            d['images'] = imgs
        out.append(d)
    return out


def has_context(msgs) -> bool:
    return any(a.get('kind') in ('shot', 'img', 'ocr', 'clip') for m in msgs[-6:] for a in m.get('attach') or ())
