"""Голос → текст: запись микрофона (WASAPI через pyaudiowpatch, без PyAudio) с автоматическим концом фразы и распознавание.
Без Qt: вызывается из рабочего потока, результат — строка или VoiceError с понятным текстом."""
import threading
import time
from core.vad import Endpointer


class VoiceError(Exception):
    pass


def to_mono16(raw: bytes, channels: int):
    import numpy as np
    a = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        a = a[:len(a) // channels * channels].reshape(-1, channels).mean(axis=1).astype(np.int16)
    return a


def rms_of(a) -> float:
    import numpy as np
    return float(np.sqrt(np.mean(a.astype(np.float64) ** 2))) if len(a) else 0.0


def record_phrase(cancel: threading.Event, capture_factory=None, ep=None):
    """Возвращает (pcm_int16_bytes, sample_rate) или бросает VoiceError."""
    import numpy as np
    from collections import deque
    chunks, pre, ep = [], deque(maxlen=4), ep or Endpointer()
    state = {'last': time.monotonic(), 'res': 'wait', 'rate': 16000}
    done = threading.Event()

    def on_data(raw, rate, ch):
        m = to_mono16(raw, ch)
        now = time.monotonic()
        dt, state['last'], state['rate'] = now - state['last'], now, rate
        res = ep.feed(rms_of(m), max(dt, 0.001))
        if ep.speaking:
            if not chunks:
                chunks.extend(pre)                       # начало фразы, записанное до срабатывания порога
            chunks.append(m)
        else:
            pre.append(m)
        state['res'] = res
        if res in ('done', 'timeout'):
            done.set()

    if capture_factory is None:
        from modules.audio_io import AudioCapture
        capture_factory = lambda cb: AudioCapture('mic', cb)
    cap = capture_factory(on_data)
    try:
        cap.start()
    except Exception as ex:
        raise VoiceError('Микрофон недоступен (установите pyaudiowpatch)') from ex
    try:
        t_end = time.monotonic() + ep.wait_max + ep.speech_max + 3.0        # страховка, если звук перестал приходить
        while not done.wait(0.05):
            if cancel.is_set():
                raise VoiceError('Отменено')
            if time.monotonic() > t_end:
                raise VoiceError('Микрофон не отвечает')
    finally:
        cap.stop()
    if state['res'] == 'timeout' or not chunks:
        raise VoiceError('Вы ничего не сказали')
    return np.concatenate(chunks).tobytes(), state['rate']


def recognize(pcm: bytes, rate: int, lang: str = 'ru-RU') -> str:
    try:
        import speech_recognition as sr
    except ImportError as ex:
        raise VoiceError('Нет пакета SpeechRecognition') from ex
    r = sr.Recognizer()
    try:
        return r.recognize_google(sr.AudioData(pcm, rate, 2), language=lang).strip()
    except sr.UnknownValueError:
        raise VoiceError('Не удалось разобрать речь') from None
    except sr.RequestError as ex:
        raise VoiceError('Нет связи с сервисом распознавания') from ex


def listen_and_recognize(cancel: threading.Event, lang='ru-RU') -> str:
    pcm, rate = record_phrase(cancel)
    return recognize(pcm, rate, lang)
