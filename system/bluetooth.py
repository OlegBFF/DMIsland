"""Bluetooth-устройства: список сопряжённых с реальным состоянием соединения и подключение/отключение."""
import ctypes
import ctypes.wintypes as wt
import time
from core.utils import log
from system.util import run_async, wr

# Major class of device → тип для значка
_MAJOR = {1: 'pc', 2: 'phone', 4: 'audio', 5: 'input', 7: 'wearable'}


async def _find_all(E, selector):
    fn = getattr(E.DeviceInformation, 'find_all_async_aqs_filter', None) or E.DeviceInformation.find_all_async
    return await fn(selector)


def devices() -> list:
    """Сопряжённые устройства (классические и BLE): [{'id','addr','name','connected','kind'}]."""
    async def go():
        BT, E = wr('windows.devices.bluetooth'), wr('windows.devices.enumeration')
        found = {}
        for cls, le in ((BT.BluetoothDevice, False), (BT.BluetoothLEDevice, True)):
            try:
                infos = await _find_all(E, cls.get_device_selector_from_pairing_state(True))
                for info in infos:
                    dev = await cls.from_id_async(info.id)
                    if dev is None:
                        continue
                    try:
                        name = dev.name or 'Устройство'
                        connected = int(getattr(dev.connection_status, 'value', dev.connection_status)) == 1
                        kind = 'other'
                        if not le:
                            kind = _MAJOR.get(int(dev.class_of_device.major_class), 'other')
                        elif 'mouse' in name.lower() or 'keyboard' in name.lower():
                            kind = 'input'
                        addr = int(dev.bluetooth_address)
                    finally:
                        try:
                            dev.close()
                        except Exception:
                            pass
                    prev = found.get(name)
                    if prev is None or (connected and not prev['connected']):
                        found[name] = {'id': f"{addr:012X}", 'addr': addr, 'name': name, 'connected': connected,
                                       'kind': kind if kind != 'other' or not prev else prev['kind']}
            except Exception as ex:
                log(f"bt list ({'le' if le else 'classic'}): {ex!r}")
        return sorted(found.values(), key=lambda d: (not d['connected'], d['name'].lower()))
    return run_async(go())


# ---------- подключение / отключение (bthprops.cpl) ----------
class _SYSTEMTIME(ctypes.Structure):
    _fields_ = [(n, wt.WORD) for n in ('year', 'month', 'dow', 'day', 'hour', 'minute', 'second', 'ms')]


class _DEVINFO(ctypes.Structure):
    _fields_ = [('dwSize', ctypes.c_uint32), ('Address', ctypes.c_ulonglong), ('ulClassofDevice', ctypes.c_uint32),
                ('fConnected', ctypes.c_int32), ('fRemembered', ctypes.c_int32), ('fAuthenticated', ctypes.c_int32),
                ('stLastSeen', _SYSTEMTIME), ('stLastUsed', _SYSTEMTIME), ('szName', ctypes.c_wchar * 248)]


class _FINDRADIO(ctypes.Structure):
    _fields_ = [('dwSize', ctypes.c_uint32)]


_SERVICES = {
    'audio': ('0000110B-0000-1000-8000-00805F9B34FB',      # A2DP sink
              '0000111E-0000-1000-8000-00805F9B34FB',      # Hands-Free
              '00001108-0000-1000-8000-00805F9B34FB'),     # Headset
    'input': ('00001124-0000-1000-8000-00805F9B34FB',),    # HID
}


def set_connected(addr: int, on: bool, kind: str = 'audio'):
    """Подключает/отключает устройство, переключая его службы (BluetoothSetServiceState).

    Публичного «connect/disconnect» у Windows нет: отключение = выключить и снова включить службы звука/ввода,
    подключение = то же самое, но с попыткой установить соединение. Работает не со всеми устройствами.
    """
    from system.power import _guid
    dll = ctypes.WinDLL('bthprops.cpl')
    dll.BluetoothFindFirstRadio.restype = ctypes.c_void_p
    dll.BluetoothFindNextRadio.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    dll.BluetoothFindRadioClose.argtypes = [ctypes.c_void_p]
    dll.BluetoothGetDeviceInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DEVINFO)]
    dll.BluetoothSetServiceState.argtypes = [ctypes.c_void_p, ctypes.POINTER(_DEVINFO), ctypes.c_void_p, ctypes.c_uint32]
    k32 = ctypes.WinDLL('kernel32')
    k32.CloseHandle.argtypes = [ctypes.c_void_p]

    params = _FINDRADIO(ctypes.sizeof(_FINDRADIO))
    radio = ctypes.c_void_p()
    hfind = dll.BluetoothFindFirstRadio(ctypes.byref(params), ctypes.byref(radio))
    if not hfind:
        raise OSError('Bluetooth-адаптер не найден или выключен')
    try:
        while True:
            info = _DEVINFO()
            info.dwSize = ctypes.sizeof(_DEVINFO)
            info.Address = addr
            if dll.BluetoothGetDeviceInfo(radio, ctypes.byref(info)) == 0:
                guids = [_guid(g) for g in _SERVICES.get(kind, _SERVICES['audio'])]
                for g in guids:
                    dll.BluetoothSetServiceState(radio, ctypes.byref(info), ctypes.byref(g), 0)    # DISABLE
                time.sleep(0.8)
                for g in guids:
                    dll.BluetoothSetServiceState(radio, ctypes.byref(info), ctypes.byref(g), 1)    # ENABLE
                return
            k32.CloseHandle(radio)
            if not dll.BluetoothFindNextRadio(hfind, ctypes.byref(radio)):
                break
        raise OSError('Устройство не найдено на адаптере')
    finally:
        dll.BluetoothFindRadioClose(hfind)
