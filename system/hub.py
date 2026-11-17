"""SystemHub: три рабочих потока (аудио / сеть / экран-питание) и Qt-сигналы с реальным состоянием системы.

Интерфейс никогда не вызывает COM, WinRT, netsh или WMI сам: он шлёт команды хабу и получает снимки состояния.
Снимок — словарь из ключей audio, wifi, wifi_networks, bt, brightness, power, winmode; хаб держит слитое состояние в .state.
"""
from PySide6.QtCore import QObject, Signal
from core.utils import log
from system import audio_ctl, bluetooth, brightness, power, radios, wifi, winmode
from system.util import com_init_mta
from system.worker import Worker


def _com_mta():
    if not com_init_mta():
        log('comtypes недоступен: громкость и устройства звука работать не будут')


class SystemHub(QObject):
    snapshot = Signal(object)            # частичный снимок (dict)
    notice = Signal(str, str, bool)      # заголовок, текст, успех

    def __init__(s):
        super().__init__()
        s.state = {}
        s.system_active = False
        s._audio = None
        s.snapshot.connect(s._store)     # первым: к моменту остальных слотов .state уже слит
        s.w_audio = Worker('audio', s._poll_audio, 0.8, _com_mta, s.snapshot.emit, s._err, gc_every=10)
        s.w_net = Worker('net', s._poll_net, 4.0, None, s.snapshot.emit, s._err)
        s.w_sys = Worker('sys', s._poll_sys, 3.0, None, s.snapshot.emit, s._err)
        for w in (s.w_audio, s.w_net, s.w_sys):
            w.start()

    def _store(s, res):
        s.state.update(res)

    def _err(s, name, ex, kind):
        log(f"hub {name} {kind}: {ex!r}")
        if kind == 'job':
            s.notice.emit('Управление системой', str(ex)[:90] or type(ex).__name__, False)

    def stop(s):
        for w in (s.w_audio, s.w_net, s.w_sys):
            w.stop()

    def set_active(s, audio: bool, system: bool):
        """audio — остров открыт (громкость на главной); system — открыта вкладка «Управление»."""
        s.system_active = system
        s.w_audio.set_active(audio)
        s.w_net.set_active(system)
        s.w_sys.set_active(system)

    def refresh(s):
        for w in (s.w_audio, s.w_net, s.w_sys):
            w.refresh()

    # ---------- опрос ----------
    def _ctl(s):
        if s._audio is None:
            s._audio = audio_ctl.AudioCtl()
        return s._audio

    def _poll_audio(s):
        return s._ctl().snapshot()

    def _poll_net(s):
        out = {}
        try:
            r = radios.states()
        except Exception as ex:
            log(f"radios: {ex!r}")
            r = {'wifi': {'present': False, 'on': False}, 'bt': {'present': False, 'on': False}}
        w = dict(r['wifi'], connected=False, ssid='', bars=0)
        if w['on']:
            try:
                w.update(wifi.current())
            except Exception as ex:
                log(f"wifi current: {ex!r}")
        out['wifi'] = w
        b = dict(r['bt'], devices=[])
        if b['on']:
            try:
                b['devices'] = bluetooth.devices()
            except Exception as ex:
                log(f"bt devices: {ex!r}")
        out['bt'] = b
        return out

    def _poll_sys(s):
        out = {}
        for key, fn in (('brightness', brightness.get), ('power', power.snapshot), ('winmode', winmode.get)):
            try:
                out[key] = fn()
            except Exception as ex:
                log(f"{key}: {ex!r}")
                out[key] = {'available': False} if key == 'brightness' else {}
        return out

    # ---------- команды: звук ----------
    def set_volume(s, v, flow='out'):
        s.w_audio.submit(lambda: s._ctl().set_volume(v, flow), key=f'vol:{flow}')

    def step_volume(s, delta, flow='out'):
        """Относительное изменение («громче», «на 10») от РЕАЛЬНОЙ громкости, а не от последнего снимка."""
        def job():
            ctl = s._ctl()
            v = max(0, min(100, ctl.get_volume(flow) + int(delta)))
            ctl.set_volume(v, flow)
            s.notice.emit('Громкость', f'{v}%', True)
        s.w_audio.submit(job, key=f'vol:{flow}')

    def set_mute(s, muted, flow='out'):
        s.w_audio.submit(lambda: s._ctl().set_mute(muted, flow), key=f'mute:{flow}')

    def toggle_mute(s, flow='out'):
        s.w_audio.submit(lambda: s._ctl().toggle_mute(flow), key=f'mute:{flow}')

    def set_default_device(s, dev_id, name=''):
        def job():
            s._ctl().set_default(dev_id)
            s.notice.emit('Аудиоустройство', name[:40] or 'Устройство по умолчанию изменено', True)
        s.w_audio.submit(job, key='default-device')

    def set_session_volume(s, app, v):
        s.w_audio.submit(lambda: s._ctl().set_session(app, volume=v), key=f'sv:{app}')

    def set_session_mute(s, app, muted):
        s.w_audio.submit(lambda: s._ctl().set_session(app, muted=muted), key=f'sm:{app}')

    # ---------- команды: сеть ----------
    def set_radio(s, name, on):
        def job():
            radios.set_state(name, on)
        s.w_net.submit(job, key=f'radio:{name}')

    def wifi_scan(s):
        def job():
            return {'wifi_networks': wifi.scan(), 'wifi_scanned': True}
        s.w_net.submit(job, key='wifi-scan')

    def wifi_connect(s, ssid, password=None):
        def job():
            res = wifi.connect(ssid, password)
            if res == 'need_password':
                return {'wifi_need_password': ssid}
            s.notice.emit('Wi-Fi', f'Подключено: {ssid}', True)
            return {'wifi_need_password': ''}
        s.w_net.submit(job, key='wifi-connect')

    def wifi_disconnect(s):
        def job():
            wifi.disconnect()
            s.notice.emit('Wi-Fi', 'Отключено', True)
        s.w_net.submit(job, key='wifi-connect')

    def bt_set_connected(s, dev, on):
        def job():
            bluetooth.set_connected(dev['addr'], on, 'input' if dev.get('kind') == 'input' else 'audio')
            s.notice.emit('Bluetooth', f"{dev['name'][:30]}: {'подключаю…' if on else 'отключено'}", True)
        s.w_net.submit(job, key=f"bt:{dev['id']}")

    # ---------- команды: экран, питание, режим ----------
    def set_brightness(s, v):
        s.w_sys.submit(lambda: brightness.set_value(v), key='brightness')

    def step_brightness(s, delta):
        def job():
            cur = brightness.get().get('value')
            if cur is None:
                raise OSError('Яркость этого экрана не управляется')
            v = max(0, min(100, cur + int(delta)))
            brightness.set_value(v)
            s.notice.emit('Яркость', f'{v}%', True)
        s.w_sys.submit(job, key='brightness')

    def set_power_mode(s, mode):
        s.w_sys.submit(lambda: power.set_mode(mode), key='power-mode')

    def set_winmode(s, system_light=None, apps_light=None):
        s.w_sys.submit(lambda: winmode.set_mode(system_light, apps_light), key='winmode')

    def toggle_winmode(s):
        s.w_sys.submit(winmode.toggle_both, key='winmode')
