"""Питание: заряд, батарейный «экономитель» и режим питания Windows (powrprof overlay)."""
import ctypes

# Режимы питания Windows 10/11 (Settings → System → Power & battery → Power mode)
MODE_GUIDS = {
    'efficiency': '961CC777-2547-4F9D-8174-7D86181B8A7A',
    'balanced': '00000000-0000-0000-0000-000000000000',
    'performance': '3AF9B8D9-7C97-431D-AD78-34A8BFEA439F',
}
_PERF_ALIASES = {'DED574B5-45A0-4F42-8737-46345C09C238'}       # «Better performance» в Windows 10


class _GUID(ctypes.Structure):
    _fields_ = [('a', ctypes.c_uint32), ('b', ctypes.c_uint16), ('c', ctypes.c_uint16), ('d', ctypes.c_ubyte * 8)]


def _guid(text: str) -> '_GUID':
    import uuid
    u = uuid.UUID(text)
    g = _GUID()
    g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
    for i, byte in enumerate(bytes([u.clock_seq_hi_variant, u.clock_seq_low]) + u.node.to_bytes(6, 'big')):
        g.d[i] = byte
    return g


def _guid_text(g: '_GUID') -> str:
    return '%08X-%04X-%04X-%02X%02X-%s' % (g.a, g.b, g.c, g.d[0], g.d[1], ''.join('%02X' % x for x in g.d[2:]))


class _SPS(ctypes.Structure):
    _fields_ = [('ac', ctypes.c_ubyte), ('flag', ctypes.c_ubyte), ('pct', ctypes.c_ubyte), ('sys', ctypes.c_ubyte),
                ('life', ctypes.c_uint32), ('full', ctypes.c_uint32)]


def get_mode():
    """'efficiency' | 'balanced' | 'performance' или None, если система режимы не поддерживает."""
    try:
        g = _GUID()
        if ctypes.windll.powrprof.PowerGetEffectiveOverlayScheme(ctypes.byref(g)) != 0:
            return None
        text = _guid_text(g)
    except (AttributeError, OSError):
        return None
    for name, guid in MODE_GUIDS.items():
        if text == guid:
            return name
    return 'performance' if text in _PERF_ALIASES else 'balanced'


def set_mode(mode: str):
    if mode not in MODE_GUIDS:
        raise ValueError(mode)
    g = _guid(MODE_GUIDS[mode])
    rc = ctypes.windll.powrprof.PowerSetActiveOverlayScheme(g)
    if rc != 0:
        raise OSError(f'PowerSetActiveOverlayScheme: код {rc}')


def snapshot() -> dict:
    st = _SPS()
    has = bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)))
    battery = has and st.flag != 128 and st.pct <= 100                  # 128 — батареи нет
    return {
        'battery': int(st.pct) if battery else None,
        'plugged': (st.ac == 1) if has and st.ac != 255 else None,
        'saver': bool(has and st.sys & 1),                              # включён системный «экономитель заряда»
        'mode': get_mode(),
    }
