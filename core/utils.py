"""Мелкие утилиты без зависимости от Qt: логирование и clamp."""
from datetime import datetime
from core.constants import LOG_PATH


def log(msg):
    """Пишет в %APPDATA%/Island/island.log (под pythonw консоли нет, поэтому ошибки не должны теряться)."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 512_000:
            LOG_PATH.write_text('', 'utf-8')
        with LOG_PATH.open('a', encoding='utf-8') as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


def clamp(v, a=0., b=1.):
    return max(a, min(b, v))
