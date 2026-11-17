"""Яркость мониторов: встроенный экран (WMI) и внешние (DDC/CI) через screen_brightness_control."""


def get() -> dict:
    import screen_brightness_control as sbc
    vals = [v for v in sbc.get_brightness() if v is not None]
    return {'available': bool(vals), 'value': round(sum(vals) / len(vals)) if vals else None, 'displays': len(vals)}


def set_value(v: int):
    import screen_brightness_control as sbc
    sbc.set_brightness(max(0, min(100, int(v))))
