"""Захват звука через WASAPI (pyaudiowpatch): системный звук (loopback) и микрофон. Без Qt — безопасно из любого потока."""
import time
from core.utils import log


class AudioCapture:
    """kind: 'loopback' — всё, что играет в устройстве вывода по умолчанию; 'mic' — микрофон по умолчанию.
    on_data(raw_int16_bytes, rate, channels) вызывается из потока PortAudio — внутри только быстрые операции."""

    def __init__(s, kind, on_data):
        s.kind, s.on_data = kind, on_data
        s.rate, s.channels, s.device_name = 0, 0, ''
        s._pa = s._stream = None
        s.last_data = 0.0

    @staticmethod
    def default_loopback_name() -> str:
        import pyaudiowpatch as pyaudio
        pa = pyaudio.PyAudio()
        try:
            return pa.get_default_wasapi_loopback()['name']
        finally:
            pa.terminate()

    def start(s):
        import pyaudiowpatch as pyaudio
        s._pa = pa = pyaudio.PyAudio()
        try:
            if s.kind == 'loopback':
                info = pa.get_default_wasapi_loopback()
            else:
                wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                info = pa.get_device_info_by_index(wasapi['defaultInputDevice'])
            s.rate, s.channels = int(info['defaultSampleRate']), max(1, int(info['maxInputChannels']))
            s.device_name = info['name']

            def cb(data, frames, tinfo, status):
                s.last_data = time.monotonic()
                try:
                    s.on_data(data, s.rate, s.channels)
                except Exception as ex:
                    log(f"audio cb {s.kind}: {ex!r}")
                return (None, pyaudio.paContinue)

            s._stream = pa.open(format=pyaudio.paInt16, channels=s.channels, rate=s.rate, input=True,
                                input_device_index=info['index'], frames_per_buffer=1024, stream_callback=cb)
        except Exception:
            s.stop()
            raise

    def stop(s):
        try:
            if s._stream is not None:
                s._stream.stop_stream()
                s._stream.close()
        except Exception:
            pass
        try:
            if s._pa is not None:
                s._pa.terminate()
        except Exception:
            pass
        s._stream = s._pa = None
