"""Реальный анализ звука для эквалайзера: FFT системного звука (WASAPI loopback) по четырём полосам.

Поток анализа ничего не знает о Qt: интерфейс просто читает `levels` (4 числа 0..1).
Если loopback недоступен, остаётся реальный пиковый уровень устройства (IAudioMeterInformation).
"""
import threading
import time
import numpy as np
from core.utils import log

BAND_EDGES = ((40, 250), (250, 1000), (1000, 4000), (4000, 14000))     # бас / низ-середина / середина-верх / верх
TILT_DB = (0.0, 6.0, 12.0, 18.0)                                        # у музыки энергия падает с частотой — выравниваем
NFFT = 2048
FLOOR_DB, TOP_DB = -66.0, -6.0


def band_db(samples, rate: int, edges=BAND_EDGES, nfft: int = NFFT):
    """Уровень (дБ относительно полной шкалы) в каждой полосе по последним nfft отсчётам моно-сигнала [-1..1]."""
    x = np.asarray(samples, dtype=np.float32)[-nfft:]
    if len(x) < nfft:
        x = np.concatenate([np.zeros(nfft - len(x), np.float32), x])
    w = np.hanning(nfft).astype(np.float32)
    amp = np.abs(np.fft.rfft(x * w)) / (w.sum() / 2.0)                  # амплитуда синусоиды A даёт пик ≈ A
    freqs = np.fft.rfftfreq(nfft, 1.0 / rate)
    out = []
    for lo, hi in edges:
        sel = (freqs >= lo) & (freqs < min(hi, rate / 2))
        e = float(np.sqrt(np.sum(amp[sel] ** 2))) if sel.any() else 0.0
        out.append(20.0 * np.log10(e + 1e-9))
    return out


def db_to_level(db: float) -> float:
    return float(min(1.0, max(0.0, (db - FLOOR_DB) / (TOP_DB - FLOOR_DB))))


def levels_from_samples(samples, rate: int):
    return [db_to_level(d + t) for d, t in zip(band_db(samples, rate), TILT_DB)]


class SpectrumAnalyzer:
    def __init__(s):
        s.levels = [0.0] * 4
        s.mode = 'off'                       # off | fft | peak
        s._stop = threading.Event()
        s._thread = None

    @property
    def running(s) -> bool:
        return s._thread is not None and s._thread.is_alive()

    def start(s):
        if s.running:
            if not s._stop.is_set():
                return
            s._thread.join(1.0)                 # предыдущий поток ещё завершается после stop()
        s._stop.clear()
        s._thread = threading.Thread(target=s._run, name='island-spectrum', daemon=True)
        s._thread.start()

    def stop(s):
        s._stop.set()

    def _run(s):
        try:
            s._run_fft()
        except Exception as ex:
            log(f"spectrum fft unavailable, using peak meter: {ex!r}")
            try:
                s._run_peak()
            except Exception as ex2:
                log(f"spectrum peak unavailable: {ex2!r}")
        s.mode, s.levels = 'off', [0.0] * 4

    def _publish(s, new):
        old = s.levels
        s.levels = [max(n, o * 0.82) for n, o in zip(new, old)]         # мгновенная атака, плавный спад

    def _run_fft(s):
        from modules.audio_io import AudioCapture
        lock = threading.Lock()
        state = {'buf': np.zeros(NFFT, np.float32), 'rate': 48000}

        def on_data(raw, rate, ch):
            a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
            mono = a.reshape(-1, ch).mean(axis=1) if ch > 1 and a.size % ch == 0 else a
            with lock:
                state['rate'] = rate
                state['buf'] = np.concatenate([state['buf'], mono])[-NFFT:]

        enum = None
        try:                                                            # дешёвая проверка смены устройства через Core Audio
            from system.audio_names import create_enumerator
            from system.util import com_gc, com_init_mta
            com_init_mta()
            enum = create_enumerator()
        except Exception as ex:
            log(f"spectrum: слежение за устройством через Core Audio недоступно ({ex!r}), использую PortAudio")
            com_gc = lambda: None                                       # noqa: E731
        from system.audio_names import default_render_id
        cap = AudioCapture('loopback', on_data)
        cap.start()
        s.mode = 'fft'
        last_id = default_render_id(enum) if enum is not None else ''
        check = time.monotonic()
        ticks = 0
        try:
            while not s._stop.wait(0.033):
                now = time.monotonic()
                if enum is not None and now - check > 2.0:              # сменили устройство вывода — переоткрываем поток
                    check = now
                    ticks += 1
                    try:
                        cur = default_render_id(enum)
                        if cur and cur != last_id:
                            last_id = cur
                            cap.stop()
                            cap.start()
                        if ticks % 15 == 0:
                            com_gc()
                    except Exception as ex:
                        log(f"spectrum reopen: {ex!r}")
                elif enum is None and now - check > 10.0:               # запасной путь: раньше PyAudio() создавался каждые 2 с
                    check = now
                    try:
                        if AudioCapture.default_loopback_name() != cap.device_name:
                            cap.stop()
                            cap.start()
                    except Exception as ex:
                        log(f"spectrum reopen: {ex!r}")
                if now - cap.last_data < 0.15:                          # loopback молчит, когда ничего не играет
                    with lock:
                        x, rate = state['buf'].copy(), state['rate']
                    s._publish(levels_from_samples(x, rate))
                else:
                    s._publish([0.0] * 4)
        finally:
            cap.stop()
            enum = None
            try:
                import gc
                gc.collect()
            except Exception:
                pass

    def _run_peak(s):
        import comtypes
        from comtypes import CLSCTX_ALL, GUID
        from pycaw.pycaw import IAudioMeterInformation, IMMDeviceEnumerator
        from system.util import com_init_mta
        com_init_mta()
        enum = comtypes.CoCreateInstance(GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}'), IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
        meter, got = None, 0.0
        s.mode = 'peak'
        weights = (1.0, 0.85, 0.7, 0.55)
        while not s._stop.wait(0.05):
            if meter is None or time.monotonic() - got > 3.0:
                dev = enum.GetDefaultAudioEndpoint(0, 0)
                meter = dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None).QueryInterface(IAudioMeterInformation)
                got = time.monotonic()
            p = float(meter.GetPeakValue()) ** 0.5
            s._publish([min(1.0, p * w) for w in weights])
