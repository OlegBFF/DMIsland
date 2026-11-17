"""Радиомодули Windows (Wi-Fi, Bluetooth): реальное состояние и включение/выключение через Windows.Devices.Radios."""
from core.utils import log
from system.util import run_async, wr

KINDS = {'wifi': 1, 'bt': 3}                      # RadioKind.WiFi = 1, RadioKind.Bluetooth = 3
_STATE = {0: 'unknown', 1: 'on', 2: 'off', 3: 'disabled'}


def _i(x) -> int:
    return int(getattr(x, 'value', x))


async def _radios():
    R = wr('windows.devices.radios')
    await R.Radio.request_access_async()
    return R, list(await R.Radio.get_radios_async())


def states() -> dict:
    """{'wifi': {'present': bool, 'on': bool}, 'bt': {...}} — по данным Windows, а не по нашим догадкам."""
    async def go():
        R, radios = await _radios()
        out = {k: {'present': False, 'on': False} for k in KINDS}
        for r in radios:
            for name, kind in KINDS.items():
                if _i(r.kind) == kind:
                    out[name]['present'] = True
                    out[name]['on'] = out[name]['on'] or _STATE.get(_i(r.state)) == 'on'
        return out
    return run_async(go())


def set_state(name: str, on: bool):
    async def go():
        R, radios = await _radios()
        mine = [r for r in radios if _i(r.kind) == KINDS[name]]
        if not mine:
            raise OSError('Адаптер не найден')
        for r in mine:
            status = await r.set_state_async(R.RadioState(1 if on else 2))
            if _i(status) != 1:                                              # RadioAccessStatus.Allowed
                raise OSError('Windows не разрешила изменить состояние адаптера (возможно, включён режим «В самолёте» '
                              'или переключатель заблокирован политикой)')
    run_async(go())
    log(f"radio {name} -> {'on' if on else 'off'}")
