"""Движок записи экрана (без Qt): весь захват, кодирование и звук живут в рабочих потоках и не трогают Qt.

Память ограничена по построению: кадры не копятся — они сразу уходят в ffmpeg/VideoWriter на диск; звук пишется
в WAV; GIF сначала пишется как короткое видео и конвертируется потоково. Длительность и свободное место на диске
контролируются в цикле записи.
"""
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
from pathlib import Path
from core.constants import REC_TMP_DIR
from core.utils import log

NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
MIN_FREE_BYTES = 300 * 1024 * 1024


def find_ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which('ffmpeg')


def frames_due(elapsed: float, fps: float, written: int, max_burst: int) -> int:
    """Сколько кадров нужно записать сейчас, чтобы видео шло в реальном времени (дубли при просадках захвата)."""
    return max(0, min(int(elapsed * fps) + 1 - written, max_burst))


def even(n: int) -> int:
    return n - (n % 2)


# ---------------- захват кадров ----------------
class Grabber:
    """Создаётся и используется ТОЛЬКО в потоке записи (дескрипторы GDI привязаны к потоку). bbox — физические пиксели."""

    def __init__(s, bbox):
        s.bbox = bbox
        s._sct = None
        try:
            import mss
            s._sct = mss.mss()
            l, t, r, b = bbox
            s._mon = {'left': l, 'top': t, 'width': r - l, 'height': b - t}
        except Exception:
            s._sct = None

    def grab(s):
        import numpy as np
        if s._sct is not None:
            return np.ascontiguousarray(np.asarray(s._sct.grab(s._mon))[:, :, :3])           # BGRA → BGR
        from PIL import ImageGrab
        return np.ascontiguousarray(np.asarray(ImageGrab.grab(bbox=s.bbox, all_screens=True))[:, :, ::-1])

    def close(s):
        try:
            if s._sct is not None:
                s._sct.close()
        except Exception:
            pass


# ---------------- запись видео ----------------
class FfmpegSink:
    def __init__(s, ffmpeg, path, w, h, fps, log_path):
        cmd = [ffmpeg, '-y', '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{w}x{h}', '-r', str(fps), '-i', '-',
               '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p', str(path)]
        s._log = open(log_path, 'wb')
        s.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=s._log, creationflags=NO_WINDOW)

    def write(s, frame):
        s.proc.stdin.write(frame.tobytes())

    def close(s):
        try:
            s.proc.stdin.close()
        except Exception:
            pass
        try:
            s.proc.wait(timeout=90)
        finally:
            s._log.close()
        if s.proc.returncode not in (0, None):
            raise OSError(f'ffmpeg завершился с кодом {s.proc.returncode}')


class CvSink:
    """Запасной вариант без ffmpeg: MPEG-4 через OpenCV, без звука."""

    def __init__(s, path, w, h, fps):
        import cv2
        s.w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'mp4v'), float(fps), (w, h))
        if not s.w.isOpened():
            raise OSError('OpenCV не смог открыть файл для записи')

    def write(s, frame):
        s.w.write(frame)

    def close(s):
        s.w.release()


# ---------------- запись звука ----------------
class AudioTrack:
    """Пишет WAV с привязкой ко времени: пока loopback молчит (кадры не приходят), добавляется тишина — звук не уезжает от видео."""

    def __init__(s, kind, wav_path, capture_factory=None):
        s.kind, s.path = kind, Path(wav_path)
        s._factory = capture_factory
        s._q = queue.Queue(maxsize=400)
        s._wav = None
        s.written = 0
        s.t0 = 0.0
        s.has_signal = False
        s._thread = None
        s.cap = None

    def start(s, t0):
        if s._factory is None:
            from modules.audio_io import AudioCapture
            s._factory = AudioCapture
        s.t0 = t0
        s.cap = s._factory(s.kind, s._on)
        s.cap.start()
        s._wav = wave.open(str(s.path), 'wb')
        s._wav.setnchannels(s.cap.channels)
        s._wav.setsampwidth(2)
        s._wav.setframerate(s.cap.rate)
        s._thread = threading.Thread(target=s._writer, daemon=True)
        s._thread.start()

    def _on(s, raw, rate, ch):
        try:
            s._q.put_nowait((time.monotonic(), bytes(raw)))
        except queue.Full:
            pass                                          # лучше потерять кусок звука, чем раздувать память

    def _silence(s, frames):
        if frames > 0:
            self_bytes = s.cap.channels * 2
            while frames > 0:
                n = min(frames, 48000)
                s._wav.writeframes(b'\x00' * (n * self_bytes))
                frames -= n
                s.written += n

    def _writer(s):
        rate, bpf = s.cap.rate, s.cap.channels * 2
        while True:
            item = s._q.get()
            if item is None:
                return
            t, raw = item
            n = len(raw) // bpf
            start_frame = int((t - s.t0) * rate) - n
            if start_frame - s.written > rate * 0.05:
                s._silence(start_frame - s.written)
            s._wav.writeframes(raw[:n * bpf])
            s.written += n
            if not s.has_signal and any(raw[:4096]):
                s.has_signal = True

    def stop(s, duration):
        try:
            s.cap.stop()
        finally:
            s._q.put(None)
            if s._thread:
                s._thread.join(timeout=5)
            s._silence(int(duration * s.cap.rate) - s.written)
            s._wav.close()


# ---------------- движок ----------------
class RecorderEngine:
    GIF_MAX_W = 640
    GIF_FPS = 10

    def __init__(s, out_path, fmt, fps, bbox, on_done, *, sys_audio=False, mic_audio=False,
                 max_seconds=1800, gif_mem_mb=64, ffmpeg='auto', grabber_factory=None, sink_factory=None):
        s.out_path, s.fmt, s.bbox, s.on_done = str(out_path), fmt, bbox, on_done
        s.fps = s.GIF_FPS if fmt == 'gif' else max(5, min(int(fps), 60))
        s.sys_audio, s.mic_audio = sys_audio and fmt != 'gif', mic_audio and fmt != 'gif'
        s.max_seconds, s.gif_mem_mb = max_seconds, gif_mem_mb
        s.ffmpeg = find_ffmpeg() if ffmpeg == 'auto' else ffmpeg
        s._grabber_factory = grabber_factory or Grabber
        s._sink_factory = sink_factory
        s.recording = False
        s.start_t = 0.0
        s._stop = threading.Event()
        s._thread = None

    def start(s):
        s.recording = True
        s.start_t = time.time()
        s._thread = threading.Thread(target=s._run, name='island-recorder', daemon=True)
        s._thread.start()

    def stop(s):
        s._stop.set()

    def join(s, timeout=None):
        if s._thread:
            s._thread.join(timeout)

    # ----- основной цикл -----
    def _fit(s, frame, size):
        if size is None:
            return frame
        w, h, scale = size
        if scale:
            import cv2
            return cv2.resize(frame, (w, h), interpolation=cv2.INTER_AREA)
        return frame[:h, :w]

    def _run(s):
        tmp = REC_TMP_DIR / uuid.uuid4().hex[:8]
        note, result = '', ''
        tracks, sink, grab = [], None, None
        try:
            tmp.mkdir(parents=True, exist_ok=True)
            grab = s._grabber_factory(s.bbox)
            first = grab.grab()
            h0, w0 = first.shape[:2]
            if s.fmt == 'gif' and w0 > s.GIF_MAX_W:
                k = s.GIF_MAX_W / w0
                size = (even(s.GIF_MAX_W), even(int(h0 * k)), True)
            else:
                size = (even(w0), even(h0), False)
            w, h, _ = size
            video = tmp / 'video.mp4'
            if s._sink_factory:
                sink = s._sink_factory(video, w, h, s.fps)
            elif s.ffmpeg:
                sink = FfmpegSink(s.ffmpeg, video, w, h, s.fps, tmp / 'ffmpeg.log')
            else:
                sink = CvSink(video, w, h, s.fps)

            t0 = time.monotonic()
            for kind, wanted in (('loopback', s.sys_audio), ('mic', s.mic_audio)):
                if wanted:
                    try:
                        tr = AudioTrack(kind, tmp / f'{kind}.wav')
                        tr.start(t0)
                        tracks.append(tr)
                    except Exception as ex:
                        log(f"rec audio {kind}: {ex!r}")
                        note = 'Звук не записан: ' + ('нужен пакет pyaudiowpatch' if isinstance(ex, ImportError) else 'устройство недоступно')
            if (s.sys_audio or s.mic_audio) and not s.ffmpeg:
                note = note or 'Звук не записан: нужен ffmpeg (pip install imageio-ffmpeg)'
                for tr in tracks:
                    tr.cap.stop()
                tracks = []

            written, last_disk = 0, t0
            frame = s._fit(first, size)
            while not s._stop.is_set():
                el = time.monotonic() - t0
                if el >= s.max_seconds:
                    note = note or f'Достигнут лимит записи: {int(s.max_seconds // 60) or 1} мин'
                    break
                if time.monotonic() - last_disk > 2:
                    last_disk = time.monotonic()
                    if shutil.disk_usage(tmp).free < MIN_FREE_BYTES:
                        note = 'Запись остановлена: мало места на диске'
                        break
                for _ in range(frames_due(el, s.fps, written, s.fps * 2)):
                    sink.write(frame)
                    written += 1
                nxt = t0 + written / s.fps
                time.sleep(max(0.0, min(nxt - time.monotonic(), 0.25)))
                frame = s._fit(grab.grab(), size)
            duration = time.monotonic() - t0
            s.recording = False
            sink.close()
            sink = None
            for tr in tracks:
                tr.stop(duration)
            result, note2 = s._finalize(tmp, video, tracks)
            note = note or note2
        except Exception as ex:
            log(f"recorder: {ex!r}")
            note, result = f'Ошибка записи: {ex}'[:80], ''
        finally:
            s.recording = False
            for tr in tracks:
                try:
                    tr.cap.stop()
                except Exception:
                    pass
            if sink is not None:
                try:
                    sink.close()
                except Exception:
                    pass
            if grab is not None:
                grab.close()
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                s.on_done(result, note)
            except Exception as ex:
                log(f"recorder on_done: {ex!r}")

    # ----- склейка и GIF -----
    def _ff(s, args, timeout=300):
        res = subprocess.run([s.ffmpeg, '-y', *args], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             timeout=timeout, creationflags=NO_WINDOW)
        if res.returncode != 0:
            raise OSError((res.stderr or b'').decode('utf-8', 'replace')[-200:])

    def _finalize(s, tmp, video, tracks):
        out = Path(s.out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if s.fmt == 'gif':
            return s._make_gif(video, out)
        wavs = [t.path for t in tracks if t.path.exists()]
        if wavs and s.ffmpeg:
            args = ['-i', str(video)] + [a for w in wavs for a in ('-i', str(w))]
            if len(wavs) == 1:
                args += ['-map', '0:v', '-map', '1:a']
            else:
                args += ['-filter_complex', '[1:a][2:a]amix=inputs=2:duration=longest:normalize=0[a]', '-map', '0:v', '-map', '[a]']
            try:
                s._ff(args + ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', str(out)])
                return str(out), ''
            except Exception as ex:
                log(f"rec mux: {ex!r}")
                shutil.move(str(video), str(out))
                return str(out), 'Звук добавить не удалось — сохранено видео без звука'
        shutil.move(str(video), str(out))
        return str(out), ''

    def _make_gif(s, video, out):
        if s.ffmpeg:
            vf = (f'fps={s.GIF_FPS},split[a][b];[a]palettegen=stats_mode=diff[p];'
                  f'[b][p]paletteuse=dither=bayer:bayer_scale=4')
            s._ff(['-i', str(video), '-vf', vf, '-loop', '0', str(out)])
            return str(out), ''
        import cv2
        from PIL import Image
        cap = cv2.VideoCapture(str(video))
        frames, used, note = [], 0, ''
        budget = s.gif_mem_mb * 1024 * 1024
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            im = Image.fromarray(fr[:, :, ::-1]).quantize(colors=128)        # 1 байт на пиксель, а не 3–4
            used += im.width * im.height
            if used > budget:
                note = 'GIF обрезан по лимиту памяти (установите imageio-ffmpeg — лимита не будет)'
                break
            frames.append(im)
        cap.release()
        if not frames:
            raise OSError('GIF: нет кадров')
        frames[0].save(str(out), save_all=True, append_images=frames[1:], duration=int(1000 / s.fps), loop=0)
        return str(out), note
