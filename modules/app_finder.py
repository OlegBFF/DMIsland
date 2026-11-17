"""Поиск программы по имени: ярлыки меню «Пуск». Без Qt."""
import os
from pathlib import Path

_SKIP = ('uninstall', 'удален', 'удалить', 'readme', 'справка', 'license', 'website')


def start_menu_roots():
    out = []
    for env in ('ProgramData', 'APPDATA'):
        base = os.environ.get(env)
        if base:
            out.append(Path(base) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs')
    return out


def find_shortcut(name: str, roots=None, limit_files: int = 4000):
    """Лучшее совпадение .lnk: точное имя → начинается с → содержит. Возвращает путь или None."""
    q = name.casefold().replace('ё', 'е').strip()
    if len(q) < 2:
        return None
    best = None
    seen = 0
    for root in (roots if roots is not None else start_menu_roots()):
        if not Path(root).exists():
            continue
        for dp, _, files in os.walk(root):
            for f in files:
                seen += 1
                if seen > limit_files:
                    return best[1] if best else None
                if not f.lower().endswith('.lnk'):
                    continue
                stem = f[:-4].casefold().replace('ё', 'е')
                if any(k in stem for k in _SKIP):
                    continue
                rank = 0 if stem == q else (1 if stem.startswith(q) else (2 if q in stem else None))
                if rank is None:
                    continue
                if best is None or (rank, len(stem)) < best[0]:
                    best = ((rank, len(stem)), os.path.join(dp, f))
    return best[1] if best else None


def find_launcher_app(name: str, apps) -> str:
    """Программа из лаунчера острова (cfg['apps']) по имени/файлу, включая группы."""
    q = name.casefold()

    def walk(items):
        for it in items:
            if it.get('type') == 'group':
                yield from walk(it.get('items', []))
            elif it.get('type', 'app') in ('app',):
                yield it
    for it in walk(apps or []):
        nm = (it.get('name') or Path(it.get('path', '')).stem).casefold()
        if nm == q or q in nm:
            return it.get('path', '')
    return ''
