"""Аудио через Core Audio: громкость, mute, устройства ввода/вывода, смена устройства по умолчанию, микшер приложений.

Все вызовы — только из потока аудио-воркера (COM в режиме MTA). Импорты pycaw/comtypes ленивые.
"""
import re
import time
from collections import OrderedDict
from ctypes import c_int, c_void_p, c_wchar_p
from core.utils import log

RENDER, CAPTURE = 0, 1
FLOW = {'out': RENDER, 'in': CAPTURE}

_PC = {}


def _policy_config():
    """Недокументированный COM-интерфейс IPolicyConfig (его же используют SoundSwitch и nircmd) — единственный
    способ сменить устройство по умолчанию программно. Порядок методов в таблице важен; неиспользуемые — заглушки."""
    if 'obj' in _PC:
        return _PC['obj']
    import comtypes
    from comtypes import COMMETHOD, GUID, HRESULT, IUnknown

    def m(name, *args):
        return COMMETHOD([], HRESULT, name, *[(['in'], t, n) for t, n in args])

    class IPolicyConfig(IUnknown):
        _iid_ = GUID('{F8679F50-850A-41CF-9C72-430F290290C8}')
        _methods_ = (
            m('GetMixFormat', (c_wchar_p, 'id'), (c_void_p, 'fmt')),
            m('GetDeviceFormat', (c_wchar_p, 'id'), (c_int, 'default'), (c_void_p, 'fmt')),
            m('ResetDeviceFormat', (c_wchar_p, 'id')),
            m('SetDeviceFormat', (c_wchar_p, 'id'), (c_void_p, 'a'), (c_void_p, 'b')),
            m('GetProcessingPeriod', (c_wchar_p, 'id'), (c_int, 'default'), (c_void_p, 'a'), (c_void_p, 'b')),
            m('SetProcessingPeriod', (c_wchar_p, 'id'), (c_void_p, 'a')),
            m('GetShareMode', (c_wchar_p, 'id'), (c_void_p, 'a')),
            m('SetShareMode', (c_wchar_p, 'id'), (c_void_p, 'a')),
            m('GetPropertyValue', (c_wchar_p, 'id'), (c_void_p, 'key'), (c_void_p, 'val')),
            m('SetPropertyValue', (c_wchar_p, 'id'), (c_void_p, 'key'), (c_void_p, 'val')),
            m('SetDefaultEndpoint', (c_wchar_p, 'id'), (c_int, 'role')),
            m('SetEndpointVisibility', (c_wchar_p, 'id'), (c_int, 'visible')),
        )
    _PC['obj'] = comtypes.CoCreateInstance(GUID('{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}'), IPolicyConfig, comtypes.CLSCTX_ALL)
    return _PC['obj']


def session_name(ses) -> str:
    """Понятное имя приложения для сессии микшера (Chrome с десятком процессов сливается в одну строку)."""
    try:
        if ses.ProcessId == 0:
            return 'Системные звуки'
        proc = ses.Process
        name = proc.name() if proc else (ses.DisplayName or '')
    except Exception:
        name = ''
    name = re.sub(r'(?i)\.exe$', '', name or '').strip()
    return name or 'Приложение'


class AudioCtl:
    NAMES_TTL = 3.0

    def __init__(s):
        s._enum = None
        s._names, s._names_t = {}, 0.0

    # ---------- низкий уровень ----------
    def _enumerator(s):
        if s._enum is None:
            import comtypes
            from comtypes import GUID
            from pycaw.pycaw import IMMDeviceEnumerator
            s._enum = comtypes.CoCreateInstance(GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}'),
                                                IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
        return s._enum

    def _default(s, flow):
        try:
            return s._enumerator().GetDefaultAudioEndpoint(flow, 0)         # eConsole
        except Exception:
            return None                                                      # устройств этого типа нет

    @staticmethod
    def _endpoint_volume(dev):
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        # ВАЖНО: не ctypes.cast(...). cast не делает AddRef, и оба указателя (исходный IUnknown и приведённый)
        # потом вызывают Release → счётчик уходит в минус, объект освобождён, а сборщик мусора позже падает
        # с access violation в comtypes.__del__ (в любом потоке). QueryInterface делает AddRef как положено.
        return dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)

    def _active_ids(s, flow):
        coll = s._enumerator().EnumAudioEndpoints(flow, 1)                   # DEVICE_STATE_ACTIVE
        return [coll.Item(i).GetId() for i in range(coll.GetCount())]

    def _device_names(s):
        if time.monotonic() - s._names_t > s.NAMES_TTL or not s._names:
            from system.audio_names import active_device_names
            s._names = active_device_names(s._enumerator())
            s._names_t = time.monotonic()
        return s._names

    # ---------- чтение ----------
    def snapshot(s) -> dict:
        names = s._device_names()
        out = {}
        for key, flow in FLOW.items():
            d = {'devices': [], 'volume': None, 'muted': False}
            try:
                dev = s._default(flow)
                default_id = dev.GetId() if dev is not None else None
                for did in s._active_ids(flow):
                    d['devices'].append({'id': did, 'name': names.get(did, 'Аудиоустройство'), 'default': did == default_id})
                if dev is not None:
                    ev = s._endpoint_volume(dev)
                    d['volume'] = round(ev.GetMasterVolumeLevelScalar() * 100)
                    d['muted'] = bool(ev.GetMute())
            except Exception as ex:
                log(f"audio snapshot {key}: {ex!r}")
            out[key] = d
        out['sessions'] = s._sessions()
        return {'audio': out}

    def _sessions(s):
        from pycaw.pycaw import AudioUtilities
        groups = OrderedDict()
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception:
            return []
        for ses in sessions:
            try:
                if ses.State == 2:                                           # AudioSessionStateExpired
                    continue
                name = session_name(ses)
                vol = ses.SimpleAudioVolume
                g = groups.setdefault(name, {'name': name, 'volume': round(vol.GetMasterVolume() * 100),
                                             'muted': bool(vol.GetMute()), 'active': False})
                g['active'] = g['active'] or ses.State == 1
            except Exception:
                continue
        return sorted(groups.values(), key=lambda g: (not g['active'], g['name'].lower()))

    # ---------- команды ----------
    def set_volume(s, v: int, flow: str = 'out'):
        dev = s._default(FLOW[flow])
        if dev is None:
            raise OSError('Нет устройства по умолчанию')
        ev = s._endpoint_volume(dev)
        ev.SetMasterVolumeLevelScalar(max(0, min(100, int(v))) / 100.0, None)
        if v > 0 and ev.GetMute():
            ev.SetMute(0, None)                                              # как в Windows: подняли громкость — звук включился

    def get_volume(s, flow: str = 'out') -> int:
        dev = s._default(FLOW[flow])
        if dev is None:
            raise OSError('Нет устройства по умолчанию')
        return round(s._endpoint_volume(dev).GetMasterVolumeLevelScalar() * 100)

    def set_mute(s, muted: bool, flow: str = 'out'):
        dev = s._default(FLOW[flow])
        if dev is None:
            raise OSError('Нет устройства по умолчанию')
        s._endpoint_volume(dev).SetMute(1 if muted else 0, None)

    def toggle_mute(s, flow: str = 'out'):
        dev = s._default(FLOW[flow])
        if dev is None:
            raise OSError('Нет устройства по умолчанию')
        ev = s._endpoint_volume(dev)
        ev.SetMute(0 if ev.GetMute() else 1, None)

    def set_default(s, dev_id: str):
        """Делает устройство основным для всех ролей (консоль, мультимедиа, связь) — как «Использовать по умолчанию»."""
        cfg = _policy_config()
        for role in (0, 1, 2):
            cfg.SetDefaultEndpoint(dev_id, role)
        s._names_t = 0.0

    def set_session(s, name: str, volume=None, muted=None):
        from pycaw.pycaw import AudioUtilities
        hit = False
        for ses in AudioUtilities.GetAllSessions():
            if session_name(ses) != name:
                continue
            vol = ses.SimpleAudioVolume
            if volume is not None:
                vol.SetMasterVolume(max(0, min(100, int(volume))) / 100.0, None)
                if volume > 0 and vol.GetMute():
                    vol.SetMute(0, None)
            if muted is not None:
                vol.SetMute(1 if muted else 0, None)
            hit = True
        if not hit:
            raise OSError(f'Приложение «{name}» больше не воспроизводит звук')
