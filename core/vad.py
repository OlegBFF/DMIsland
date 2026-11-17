"""Определение конца фразы по громкости (без Qt и звуковых библиотек — тестируется на готовых числах)."""


class Endpointer:
    """feed(rms, dt) → 'wait' (ждём речь) | 'speech' | 'done' (речь закончилась) | 'timeout' (так и не заговорили).
    Порог берётся от фонового шума первых ambient секунд."""

    def __init__(s, ambient=0.4, wait_max=6.0, silence_end=1.0, speech_max=12.0, min_thr=350.0, factor=2.6):
        s.ambient, s.wait_max, s.silence_end, s.speech_max = ambient, wait_max, silence_end, speech_max
        s.min_thr, s.factor = min_thr, factor
        s.t = s.noise_sum = s.noise_n = 0
        s.thr = None
        s.speaking = False
        s.speech_t = s.silent = 0.0

    def feed(s, rms: float, dt: float) -> str:
        s.t += dt
        if s.thr is None:
            s.noise_sum += rms
            s.noise_n += 1
            if s.t >= s.ambient:
                s.thr = max(s.min_thr, s.factor * s.noise_sum / max(s.noise_n, 1))
            return 'wait'
        if rms >= s.thr:
            s.speaking, s.silent = True, 0.0
        elif s.speaking:
            s.silent += dt
        if s.speaking:
            s.speech_t += dt
            if s.silent >= s.silence_end or s.speech_t >= s.speech_max:
                return 'done'
            return 'speech'
        return 'timeout' if s.t >= s.wait_max else 'wait'
