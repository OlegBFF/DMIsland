"""Скриншоты, OCR, QR, пипетка, загрузка изображений."""
import asyncio
import base64
import json
import threading
import urllib.parse
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QBuffer, QIODevice, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPixmap
from core.config import save_cfg
from core.constants import SHOTS_DIR
from core.security import dpapi_decrypt, safe_urlopen
from ui.overlays import SnapOverlay
from ui.themes import wr
from ui.widgets import thumb


def ocr_png_bytes(png_bytes: bytes) -> str:
    """Windows OCR по PNG из памяти (языки профиля пользователя). Вызывать из рабочего потока."""
    async def _ocr():
        OcrEngine = wr('windows.media.ocr').OcrEngine
        Streams = wr('windows.storage.streams')
        BitmapDecoder = wr('windows.graphics.imaging').BitmapDecoder
        mem = Streams.InMemoryRandomAccessStream()
        writer = Streams.DataWriter(mem)
        writer.write_bytes(png_bytes)
        await writer.store_async()
        await writer.flush_async()
        mem.seek(0)
        dec = await BitmapDecoder.create_async(mem)
        bmp = await dec.get_software_bitmap_async()
        eng = OcrEngine.try_create_from_user_profile_languages()
        res = await eng.recognize_async(bmp)
        return '\n'.join(line.text for line in res.lines)
    return asyncio.run(_ocr()).strip()


class CaptureMixin:
    """Часть класса Island: CaptureMixin."""

    def grab(s):
        scr = s.get_target_screen()
        pm = scr.grabWindow(0)
        pm.setDevicePixelRatio(scr.devicePixelRatio())
        return pm

    def snap(s, mode):
        s.mode = 'idle'
        QTimer.singleShot(110, lambda: setattr(s, 'ov', SnapOverlay(s.grab(), mode, s)))

    def full_shot(s):
        s.save_shot(s.grab(), upload=False)

    def save_shot(s, pm, upload=False):
        SHOTS_DIR.mkdir(parents=True, exist_ok=True)
        fp = SHOTS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.png"
        pm.save(str(fp))
        s.mute = True
        QGuiApplication.clipboard().setPixmap(pm)
        s.clips.add_file_item('img', str(fp), f"Скриншот {pm.width()}×{pm.height()}", owned=False)
        s.refresh_clip()
        QTimer.singleShot(400, lambda: setattr(s, 'mute', False))
        s.pop('Скриншот готов', f"В буфере и в папке · {pm.width()}×{pm.height()}", thumb(pm, 96))
        if upload:
            s.upload_image(str(fp))

    def upload_image(s, fp):
        srv = s.cfg.get('upload_service', 'none')
        key = dpapi_decrypt(s.cfg.get('upload_key_enc', '')).strip()
        if srv == 'none' or not key:
            s.pop('Загрузка отключена', 'Укажите ключ ImgBB / Imgur в Настройках', (QColor('#ff9f0a'), 'area'))
            return
        def run():
            try:
                b64 = base64.b64encode(Path(fp).read_bytes()).decode()
                if srv == 'imgbb':
                    data = urllib.parse.urlencode({'key': key, 'image': b64}).encode()
                    raw = safe_urlopen('https://api.imgbb.com/1/upload', data=data, timeout=15)
                    url = json.loads(raw.decode())['data']['url']
                else:
                    data = urllib.parse.urlencode({'image': b64}).encode()
                    raw = safe_urlopen('https://api.imgur.com/3/image', data=data,
                                       headers={'Authorization': f'Client-ID {key}'}, timeout=15)
                    url = json.loads(raw.decode())['data']['link']
                s.clipTextSignal.emit(url)                 # из рабочего потока буфер Qt трогать нельзя
                s.toastSignal.emit('Ссылка в буфере', url, (QColor('#34c759'), 'clip'), 4.0)
            except Exception as e:
                s.toastSignal.emit('Ошибка загрузки', str(e)[:40], (QColor('#ff453a'), 'area'), 4.0)
        threading.Thread(target=run, daemon=True).start()

    def on_color_picked(s, col):
        hx = col.name().upper()
        QGuiApplication.clipboard().setText(hx)
        ch = [hx] + [c for c in s.cfg.get('color_history', []) if c != hx][:5]
        s.cfg['color_history'] = ch
        save_cfg(s.cfg)
        s.pop(f"{hx} в буфере", f"rgb({col.red()}, {col.green()}, {col.blue()})", col, 4.0)

    def run_ocr_ram(s, pm: QPixmap):
        """Распознаёт текст с экрана полностью в оперативной памяти (без записи временных файлов на диск)."""
        ba = QBuffer()
        ba.open(QIODevice.WriteOnly)
        pm.save(ba, 'PNG')
        png_bytes = bytes(ba.data())
        def run():
            try:
                txt = ocr_png_bytes(png_bytes)
                if txt:
                    s.clipTextSignal.emit(txt)
                    s.toastSignal.emit('Текст с экрана в буфере', txt[:48], (QColor('#34c759'), 'ocr'), 4.0)
                else:
                    s.toastSignal.emit('Текст не найден', 'Попробуйте выделить крупнее', (QColor('#ff9f0a'), 'ocr'), 3.0)
            except Exception:
                s.toastSignal.emit('OCR Windows', 'Установите winrt-Windows.Media.Ocr', (QColor('#ff453a'), 'ocr'), 4.0)
        threading.Thread(target=run, daemon=True).start()

    def run_qr_ram(s, pm: QPixmap):
        """Декодирует QR-код напрямую из буфера в оперативной памяти."""
        try:
            import cv2, numpy as np
            img = pm.toImage().convertToFormat(QImage.Format_RGBA8888)
            arr = np.frombuffer(img.bits(), np.uint8).reshape((img.height(), img.width(), 4))
            bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
            val, _, _ = cv2.QRCodeDetector().detectAndDecode(bgr)
            if val:
                QGuiApplication.clipboard().setText(val)
                s.pop('QR-код в буфере', val[:46], (QColor('#34c759'), 'qr'), 4.0)
            else:
                s.pop('QR-код не найден', 'Выделите код чётче', (QColor('#ff9f0a'), 'qr'), 3.0)
        except Exception:
            s.pop('QR-сканер', 'Требуется пакет opencv-python', (QColor('#ff453a'), 'qr'), 3.5)
