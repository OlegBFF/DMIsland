"""Wi-Fi: текущее подключение (netsh), список сетей и подключение (Windows.Devices.WiFi)."""
import math
import re
from system.util import run_async, run_hidden, wr


def parse_interfaces(text: str) -> dict:
    """Разбор `netsh wlan show interfaces` независимо от языка Windows: SSID не переводится, сигнал — строка с «NN%»."""
    ssid, signal = '', None
    for line in text.splitlines():
        m = re.match(r'^\s*SSID\s*:\s*(.*?)\s*$', line)                      # BSSID сюда не попадает
        if m and m.group(1) and not ssid:
            ssid = m.group(1)
        m = re.search(r':\s*(\d{1,3})\s*%\s*$', line)
        if m and signal is None:
            signal = min(100, int(m.group(1)))
    return {'connected': bool(ssid), 'ssid': ssid, 'bars': math.ceil(signal / 25) if signal is not None and ssid else 0}


def current() -> dict:
    return parse_interfaces(run_hidden(['netsh', 'wlan', 'show', 'interfaces']))


def disconnect():
    run_hidden(['netsh', 'wlan', 'disconnect'])


# NetworkAuthenticationType: None=0, Unknown=1, Open80211=2, ... всё остальное требует пароль
_OPEN = {0, 1, 2}


async def _adapter():
    W = wr('windows.devices.wifi')
    access = await W.WiFiAdapter.request_access_async()
    if int(getattr(access, 'value', access)) != 1:
        raise OSError('Нет доступа к Wi-Fi (Параметры → Конфиденциальность → Расположение / Wi-Fi)')
    adapters = await W.WiFiAdapter.find_all_adapters_async()
    if not len(adapters):
        raise OSError('Wi-Fi адаптер не найден')
    return W, adapters[0]


def _network_list(ad, current_ssid: str = ''):
    best = {}
    for n in ad.network_report.available_networks:
        ssid = n.ssid
        if not ssid:
            continue
        auth = int(getattr(n.security_settings.network_authentication_type, 'value', n.security_settings.network_authentication_type))
        row = {'ssid': ssid, 'bars': int(n.signal_bars), 'secured': auth not in _OPEN, 'connected': ssid == current_ssid}
        if ssid not in best or row['bars'] > best[ssid]['bars']:
            best[ssid] = row
    return sorted(best.values(), key=lambda r: (not r['connected'], -r['bars'], r['ssid'].lower()))


def scan() -> list:
    cur = current()['ssid']

    async def go():
        W, ad = await _adapter()
        await ad.scan_async()
        return _network_list(ad, cur)
    return run_async(go())


_STATUS = {0: 'неизвестная ошибка', 2: 'доступ отозван', 3: 'неверный пароль', 4: 'сеть недоступна',
           5: 'истекло время ожидания', 6: 'неподдерживаемый тип защиты'}


def connect(ssid: str, password: str = None) -> str:
    """'ok' | 'need_password'. Для известных Windows сетей пароль не нужен."""
    async def go():
        W, ad = await _adapter()
        await ad.scan_async()
        net = next((n for n in ad.network_report.available_networks if n.ssid == ssid), None)
        if net is None:
            raise OSError('Сеть не найдена — обновите список')
        kind = W.WiFiReconnectionKind.AUTOMATIC
        if password:
            C = wr('windows.security.credentials')
            cred = C.PasswordCredential()
            cred.password = password
            res = await ad.connect_with_password_credential_async(net, kind, cred)
        else:
            res = await ad.connect_async(net, kind)
        code = int(getattr(res.connection_status, 'value', res.connection_status))
        if code == 1:
            return 'ok'
        if code == 3 and not password:
            return 'need_password'
        raise OSError(f"Не удалось подключиться: {_STATUS.get(code, f'код {code}')}")
    return run_async(go())
