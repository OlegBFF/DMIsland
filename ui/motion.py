"""Сценарии движения острова: как именно он раскрывается для меню, уведомления, музыки и системных событий. Без Qt.

Размеры острова двигают две независимые пружины (ширина и высота). Сценарий меняет их жёсткость/затухание относительно
стиля анимации из настроек и задаёт задержку одной оси относительно другой — отсюда «растягивание капсулы»:
при раскрытии капсула сначала тянется в стороны и только потом опускается; уведомление «шлёпается» вниз и пружинит; музыка
растёт мягко и медленно; системное событие — быстрый «поп».
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    kw: float                # жёсткость пружины ширины (при стиле «Жидкая»)
    dw: float                # «сохранение скорости» ширины: больше — дольше качается (≈0.50 без отскока … 0.60 заметный отскок)
    kh: float
    dh: float
    w_delay: float = 0.0     # секунд до начала движения ширины
    h_delay: float = 0.0
    duration: float = 0.9    # сколько секунд сценарий считается «активным»


# Подобрано численно (см. tests/test_motion.py): перелёт указан для основного размера.
SCENARIOS = {
    'open': Scenario(kw=.24, dw=.55, kh=.15, dh=.60, h_delay=.05),                    # в стороны (≈7%), затем вниз «желе» (≈5%)
    'close': Scenario(kw=.17, dw=.50, kh=.17, dh=.50, w_delay=.06),                    # без отскока: мягкая посадка
    'notif': Scenario(kw=.20, dw=.55, kh=.24, dh=.56, w_delay=.03),                    # быстрый «шлёп» вниз (≈8%), ширина догоняет
    'toast': Scenario(kw=.26, dw=.57, kh=.20, dh=.55),                                 # упругий «поп»
    'media': Scenario(kw=.12, dw=.60, kh=.12, dh=.60, duration=1.4),                   # музыка и запись: медленно и плавно
}


def scenario_for(prev_mode: str, mode: str, reason: str = '') -> str:
    """Какой сценарий включить при смене режима (или ширины «таблетки» в простое: reason='media')."""
    if reason == 'media':
        return 'media'
    if mode in ('open', 'notif', 'toast'):
        return mode
    return 'close'


class Motion:
    """Текущий сценарий и его «часы». params() отдаёт (kw, dw, kh, dh, ширина_двигается, высота_двигается)."""

    def __init__(s):
        s.name, s.t0 = 'close', -1e9

    def start(s, name: str, now: float):
        s.name, s.t0 = name, now

    def params(s, now: float, style_k: float, style_d: float):
        """style_k/style_d — стиль анимации из настроек: «Жидкая» (0.20/0.68) = сценарий как есть, «Резкая» жёстче,
        «Плавная» мягче и без отскока."""
        sc = SCENARIOS[s.name]
        age = now - s.t0
        if age > sc.duration + 0.3:
            return style_k, style_d, style_k, style_d, True, True
        scale, shift = style_k / 0.20, (style_d - 0.68) * 0.6
        cd = lambda v: max(0.35, min(0.82, v + shift))
        return (sc.kw * scale, cd(sc.dw), sc.kh * scale, cd(sc.dh), age >= sc.w_delay, age >= sc.h_delay)
