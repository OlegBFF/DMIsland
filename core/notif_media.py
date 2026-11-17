"""Картинки из уведомлений: по ссылке (только по явному нажатию) и локальные файлы. Без Qt."""
from pathlib import Path
from core.security import safe_urlopen

MAX_LOCAL_BYTES = 10 * 1024 * 1024
_MAGIC = ((b'\x89PNG\r\n\x1a\n', 'png'), (b'\xff\xd8\xff', 'jpg'), (b'GIF87a', 'gif'), (b'GIF89a', 'gif'), (b'BM', 'bmp'))


def sniff_image(data: bytes):
    """Тип изображения по первым байтам или None (SVG и всё прочее отбрасывается)."""
    for sig, kind in _MAGIC:
        if data.startswith(sig):
            return kind
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None


def fetch_image_bytes(url: str) -> bytes:
    """Скачивает картинку по https (лимит 2 МБ из safe_urlopen). Бросает ValueError, если это не изображение."""
    data = safe_urlopen(url, headers={'User-Agent': 'IslandPro/5.5', 'Accept': 'image/*'}, timeout=8)
    if not sniff_image(data):
        raise ValueError('по ссылке не изображение')
    return data


def read_local_image(path: str) -> bytes:
    p = Path(path)
    if p.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp') or str(p).startswith('\\\\'):
        raise ValueError('не картинка')
    if not p.is_file() or p.stat().st_size > MAX_LOCAL_BYTES:
        raise ValueError('файл недоступен или слишком большой')
    data = p.read_bytes()
    if not sniff_image(data):
        raise ValueError('не изображение')
    return data
