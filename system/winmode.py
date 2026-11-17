"""Режим Windows: светлый/тёмный для системы (панель задач, «Пуск») и для приложений — отдельно."""
import ctypes

_KEY = r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'


def get() -> dict:
    import winreg
    out = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY) as k:
        for name, key in (('system_light', 'SystemUsesLightTheme'), ('apps_light', 'AppsUseLightTheme')):
            try:
                out[name] = winreg.QueryValueEx(k, key)[0] == 1
            except OSError:
                out[name] = True
    return out


def set_mode(system_light=None, apps_light=None):
    """None — не менять. Записывает в реестр и рассылает WM_SETTINGCHANGE, чтобы окна перекрасились."""
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as k:
        if system_light is not None:
            winreg.SetValueEx(k, 'SystemUsesLightTheme', 0, winreg.REG_DWORD, int(bool(system_light)))
        if apps_light is not None:
            winreg.SetValueEx(k, 'AppsUseLightTheme', 0, winreg.REG_DWORD, int(bool(apps_light)))
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x1A, 0, 'ImmersiveColorSet', 2, 2000, None)


def toggle_both():
    cur = get()
    light = not (cur['system_light'] and cur['apps_light'])     # если хоть что-то тёмное — делаем всё светлым, иначе всё тёмным
    set_mode(light, light)
    return light
