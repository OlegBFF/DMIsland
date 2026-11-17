"""История буфера обмена: SQLite, поиск, избранное, защита секретных данных."""
import hashlib
import subprocess
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, QMimeData, QSize, QTimer, QUrl, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QListWidgetItem, QMenu
from core.constants import CLIP_IMG_DIR
from core.utils import log
from ui.widgets import thumb

# Менеджеры паролей (KeePass, 1Password, Bitwarden…) помечают скопированный секрет этими форматами Windows
_NO_HISTORY_FORMATS = ('ExcludeClipboardContentFromMonitorProcessing',)
_CAN_INCLUDE = 'CanIncludeInClipboardHistory'
MAX_IMAGE_BYTES = 30 * 1024 * 1024


class ClipboardMixin:
    """Часть класса Island: ClipboardMixin."""

    def clip_opts(s):
        c = s.cfg
        return dict(max_items=int(c.get('clip_max_items', 300)), keep_days=int(c.get('clip_keep_days', 30)),
                    secret_ttl=int(c.get('clip_secret_ttl', 120)), secret_policy=c.get('clip_secret_policy', 'mask'),
                    heuristic=bool(c.get('clip_secret_heuristic', True)))

    def apply_clip_options(s):
        s.clips.configure(**s.clip_opts())

    @staticmethod
    def _clip_excluded(md) -> bool:
        """True, если источник просит не сохранять содержимое (парольные менеджеры)."""
        for f in md.formats():
            if any(x in f for x in _NO_HISTORY_FORMATS):
                return True
            if _CAN_INCLUDE in f:
                raw = bytes(md.data(f))
                if raw and int.from_bytes(raw[:4], 'little') == 0:
                    return True
        return False

    def clip_changed(s):
        if s.mute:
            return
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md is None or s._clip_excluded(md):
            return
        try:
            if md.hasImage():
                s._clip_store_image(cb.image())
            elif md.hasText():
                s.clips.add_text(cb.text())
        except Exception as ex:
            log(f"clip_changed: {ex!r}")
        s.refresh_clip()

    def _clip_store_image(s, img: QImage):
        if img.isNull() or img.width() * img.height() > 40_000_000:
            return
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        img.save(buf, 'PNG')
        data = bytes(buf.data())
        if not data or len(data) > MAX_IMAGE_BYTES:
            return
        digest = hashlib.sha1(data).hexdigest()
        CLIP_IMG_DIR.mkdir(parents=True, exist_ok=True)
        fp = CLIP_IMG_DIR / f"{digest[:20]}.png"
        if not fp.exists():
            fp.write_bytes(data)
        s.clips.add_file_item('img', str(fp), f'Изображение {img.width()}×{img.height()}', owned=True, digest=digest)

    def on_clip_text(s, text):
        """Слот для рабочих потоков (OCR, голос, загрузка): буфер обмена Qt трогаем только в главном потоке."""
        QGuiApplication.clipboard().setText(text)

    def clip_maintenance(s):
        """Раз в несколько секунд: просроченные секреты и старые записи удаляются."""
        try:
            if s.clips.prune():
                s.refresh_clip()
        except Exception as ex:
            log(f"clip_maintenance: {ex!r}")

    # ---------- список ----------
    def _clip_icon(s, path):
        ic = s.clip_icons.get(path)
        if ic is None:
            pm = QPixmap(path)
            ic = QIcon(thumb(pm, 36)) if not pm.isNull() else QIcon()
            if len(s.clip_icons) > 200:
                s.clip_icons.clear()
            s.clip_icons[path] = ic
        return ic

    def refresh_clip(s):
        if not hasattr(s, 'lw'):
            return
        s.lw.clear()
        for item in s.clips.items(s.q.text(), s.clip_fav_only):
            prefix = ('★ ' if item['favorite'] else '') + ('🔒 ' if item['secret'] else '')
            it = QListWidgetItem(prefix + item['text'].replace('\n', ' ')[:85])
            if item['kind'] == 'img' and item['path']:
                it.setIcon(s._clip_icon(item['path']))
            elif item['kind'] == 'file':
                it.setToolTip(item['path'] or '')
            it.setData(Qt.UserRole, item)
            s.lw.addItem(it)
        s.clip_count.setText(f"{s.lw.count()}")

    def set_clip_fav_filter(s, fav):
        s.clip_fav_only = fav
        s.clip_all_btn.setChecked(not fav)
        s.clip_fav_btn.setChecked(fav)
        s.refresh_clip()

    def _clip_mute(s):
        s.mute = True
        QTimer.singleShot(400, lambda: setattr(s, 'mute', False))

    def pick_clip(s, it):
        item = it.data(Qt.UserRole)
        cb = QGuiApplication.clipboard()
        s._clip_mute()
        label = item['text'][:42]
        if item['secret']:
            val = s.clips.secret_value(item['id'])
            if val is None:
                s.pop('Срок хранения истёк', 'Секретная запись удалена', (QColor('#ff9f0a'), 'clip'))
                s.clips.prune()
                s.refresh_clip()
                return
            cb.setText(val)
            QTimer.singleShot(30_000, lambda v=val: s._clear_secret_clip(v))     # секрет не остаётся в буфере надолго
            label = 'Секрет · буфер очистится через 30 с'
        elif item['kind'] == 'img' and item['path'] and Path(item['path']).exists():
            cb.setImage(QImage(item['path']))
        elif item['kind'] == 'file' and item['path'] and Path(item['path']).exists():
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(item['path'])])
            cb.setMimeData(md)
        else:
            cb.setText(item['text'])
        s.clips.touch(item['id'])
        s.pop('Скопировано', label, (QColor('#34c759'), 'clip'))

    def _clear_secret_clip(s, val):
        cb = QGuiApplication.clipboard()
        if cb.text() == val:
            s._clip_mute()
            cb.clear()

    def clip_menu(s, pos):
        it = s.lw.itemAt(pos)
        if not it:
            return
        item = it.data(Qt.UserRole)
        m = s.mk_menu()
        a_copy = m.addAction('Копировать')
        a_fav = m.addAction('Убрать из избранного' if item['favorite'] else 'В избранное')
        a_open = m.addAction('Показать в папке') if item.get('path') else None
        m.addSeparator()
        a_del = m.addAction('Удалить')
        res = m.exec(s.lw.mapToGlobal(pos))
        if res is None:
            return
        if res == a_copy:
            s.pick_clip(it)
        elif res == a_fav:
            s.clips.set_favorite(item['id'], not item['favorite'])
            s.refresh_clip()
        elif a_open and res == a_open and Path(item['path']).exists():
            subprocess.Popen(['explorer', '/select,', str(Path(item['path']).resolve())])
        elif res == a_del:
            s.clips.delete(item['id'])
            s.refresh_clip()

    def clip_clear(s):
        s.clips.clear(keep_favorites=True)
        s.refresh_clip()

    def plain(s):
        c = QGuiApplication.clipboard()
        c.setText(c.text())
        s.pop('Чистый текст', 'Форматирование убрано', (QColor('#0a84ff'), 'plain'))
