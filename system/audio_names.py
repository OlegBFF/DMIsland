"""Имена активных аудиоустройств БЕЗ pycaw.AudioUtilities.GetAllDevices().

GetAllDevices() перебирает ВСЕ свойства ВСЕХ устройств (даже отключённых) и на каждом сбойном свойстве
сыплет UserWarning «COMError attempting to get property 63/64». Он вызывался каждые пару секунд из двух потоков,
плодил сотни COM-объектов, которые потом освобождались из «чужого» потока — отсюда лавина
«Exception ignored in __del__ ... access violation». Здесь читается ровно одно свойство — FriendlyName.

Вызывать только из потока, где инициализирован COM. Импорты pycaw/comtypes ленивые.
"""
import warnings

FRIENDLY_FMTID = 'a45c254e-df1c-4efd-8020-67d146a850e0'     # PKEY_Device_FriendlyName = {fmtid}, 14
FRIENDLY_PID = 14
DEVICE_STATE_ACTIVE = 1
_legacy_only = False                                        # если прямой способ не заработал — один раз переходим на старый


def create_enumerator():
    import comtypes
    from comtypes import GUID
    from pycaw.pycaw import IMMDeviceEnumerator
    return comtypes.CoCreateInstance(GUID('{BCDE0395-E52F-467C-8E3D-C4579291692E}'),
                                     IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)


def default_render_id(enum=None) -> str:
    """Id устройства вывода по умолчанию (дёшево, без PortAudio); '' — устройства нет."""
    try:
        return (enum or create_enumerator()).GetDefaultAudioEndpoint(0, 0).GetId()      # eRender, eConsole
    except Exception:
        return ''


def friendly_name(dev) -> str:
    """Имя устройства из его хранилища свойств; '' если не удалось."""
    store = dev.OpenPropertyStore(0)                        # STGM_READ
    if store is None:
        return ''
    for j in range(store.GetCount()):
        try:
            pk = store.GetAt(j)
            if int(pk.pid) != FRIENDLY_PID or str(pk.fmtid).strip('{}').lower() != FRIENDLY_FMTID:
                continue
            val = store.GetValue(pk)
            try:
                return str(val.GetValue() or '')
            finally:
                try:
                    val.clear()
                except Exception:
                    pass
        except Exception:
            continue
    return ''


def _legacy(enum_unused=None) -> dict:
    from pycaw.pycaw import AudioUtilities
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return {d.id: d.FriendlyName for d in AudioUtilities.GetAllDevices()
                if getattr(d, 'FriendlyName', None) and str(getattr(d, 'state', 'active')).lower().endswith('active')}


def active_device_names(enum=None) -> dict:
    """{id устройства: имя} для активных устройств вывода и ввода."""
    global _legacy_only
    if _legacy_only:
        return _legacy()
    try:
        enum = enum or create_enumerator()
        out = {}
        for flow in (0, 1):                                 # eRender, eCapture
            coll = enum.EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE)
            for i in range(coll.GetCount()):
                dev = coll.Item(i)
                out[dev.GetId()] = friendly_name(dev) or 'Аудиоустройство'
        return out
    except Exception:
        if _legacy_only:
            raise
        _legacy_only = True                                 # не мучаем себя: дальше — старый способ без предупреждений
        from core.utils import log
        import traceback
        log('audio_names: прямое чтение имён не сработало, перехожу на pycaw\n' + traceback.format_exc())
        return _legacy()
