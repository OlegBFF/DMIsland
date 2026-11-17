"""Island Launcher: один файл (или IslandLauncher.exe), который сам готовит окружение и запускает остров.

Что делает по шагам:
  1. находит main.py острова (рядом с лаунчером или в подпапке Island);
  2. ищет Python 3.10+ (64-бит); если его нет — предлагает поставить через winget или открывает python.org;
  3. создаёт изолированное окружение %LOCALAPPDATA%\\IslandPro\\venv и ставит туда библиотеки из requirements.txt
     (повторно — только если requirements.txt изменился или окружение сломалось);
  4. запускает остров БЕЗ консоли, а весь его вывод пишет в %APPDATA%\\Island\\run.log;
  5. если остров вылетел — показывает окно с причиной (вывод процесса, island.log, crash.log) и кнопками
     «Перезапустить / Копировать / Открыть папку логов».

Только стандартная библиотека; tkinter подключается лениво, поэтому вся логика проверяется тестами без окна.
Сборка в exe: build_exe.bat (PyInstaller). Без сборки можно запускать двойным кликом по Island.pyw.
"""
import hashlib
import json
import os
import queue
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

APP = 'Island Pro'
PUBLISHER = 'OlegBFF'
APP_VERSION = (5, 5, 0, 0)
BRAND_EXE = 'IslandPro.exe'                              # копия python.exe из venv с нашей версионной информацией
WIN = sys.platform == 'win32'
CREATE_NO_WINDOW = 0x08000000 if WIN else 0
MIN_PY = (3, 10)
PREFERRED = ((3, 13), (3, 12), (3, 11), (3, 10))        # на них собраны все колёса из requirements.txt
CRITICAL = ('pyside6', 'psutil', 'comtypes', 'pycaw')   # без них остров не запустится; остальное — отдельные функции
IMPORT_CHECK = 'import PySide6.QtCore, psutil' + ('; import comtypes, pycaw.pycaw' if WIN else '')
WINGET_ID = 'Python.Python.3.13'
PYTHON_URL = 'https://www.python.org/downloads/windows/'
CRASH_LOOP = (3, 300)                                    # 3 сбоя за 5 минут — автоперезапуск прекращается
AUTO_RESTART_DELAY = 10


class SetupError(Exception):
    """Подготовка окружения не удалась; текст показывается пользователю как есть."""


# ==================== ПУТИ ====================
class Paths:
    def __init__(s, base=None, appdata=None, localappdata=None):
        if base is None:
            base = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
        s.base = Path(base)
        home = Path.home()
        s.data = Path(appdata or os.getenv('APPDATA') or home / '.config') / 'Island'            # там же остров держит свои логи
        s.tool = Path(localappdata or os.getenv('LOCALAPPDATA') or home / '.local' / 'share') / 'IslandPro'
        s.venv = s.tool / 'venv'
        s.stamp = s.tool / 'requirements.stamp'
        s.settings = s.tool / 'launcher.json'
        s.run_log = s.data / 'run.log'
        s.island_log = s.data / 'island.log'
        s.crash_log = s.data / 'crash.log'
        s.launcher_log = s.data / 'launcher.log'
        s.last_crash = s.data / 'last_crash.txt'

    def project(s):
        for c in (s.base, s.base / 'Island', s.base.parent):
            if (c / 'main.py').is_file() and (c / 'core' / 'app.py').is_file():
                return c
        return None

    def venv_python(s):
        return s.venv / ('Scripts/python.exe' if WIN else 'bin/python')


def clean_env(extra=None):
    """Окружение для дочерних процессов: без хвостов PyInstaller, которые ломают чужой Python."""
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ('PYTHONHOME', 'PYTHONPATH', '_MEIPASS2', 'TCL_LIBRARY', 'TK_LIBRARY') and not k.startswith('_PYI')}
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PIP_DISABLE_PIP_VERSION_CHECK'] = '1'
    env.update(extra or {})
    return env


def run_stream(cmd, log, cwd=None, env=None, timeout=None) -> int:
    """Запускает команду без окна, строки вывода отдаёт в log(); возвращает код выхода (-1 — не запустилась / таймаут)."""
    log('> ' + ' '.join(str(c) for c in cmd))
    try:
        p = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=env or clean_env(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                             errors='replace', creationflags=CREATE_NO_WINDOW)
    except OSError as ex:
        log(f'не удалось запустить: {ex}')
        return -1
    timer = None
    if timeout:
        timer = threading.Timer(timeout, p.kill)
        timer.start()
    try:
        for line in p.stdout:
            line = line.rstrip()
            if line:
                log(line)
        return p.wait()
    finally:
        if timer:
            timer.cancel()


# ==================== PYTHON ====================
def probe_python(cmd):
    """(major, minor, micro, bits) для команды-интерпретатора или None, если это не рабочий Python
    (в Windows `python` бывает заглушкой Microsoft Store — она не отвечает версией)."""
    try:
        r = subprocess.run([str(c) for c in cmd] + ['-c', 'import sys,struct;print(*sys.version_info[:3],struct.calcsize("P")*8)'],
                           capture_output=True, text=True, timeout=20, creationflags=CREATE_NO_WINDOW,
                           stdin=subprocess.DEVNULL, env=clean_env())
        m = re.fullmatch(r'(\d+) (\d+) (\d+) (\d+)', (r.stdout or '').strip())
        return tuple(int(x) for x in m.groups()) if r.returncode == 0 and m else None
    except (OSError, subprocess.SubprocessError):
        return None


def candidate_pythons():
    c = []
    if not getattr(sys, 'frozen', False):
        exe = sys.executable
        if exe.lower().endswith('pythonw.exe'):                 # pythonw молчит в stdout — для проверки версии нужен python.exe
            exe = exe[:-11] + 'python.exe'
        c.append([exe])
    if WIN:
        c += [['py', f'-{a}.{b}'] for a, b in PREFERRED]
    c += [['python'], ['python3']]
    if WIN:
        roots = [os.getenv('LOCALAPPDATA') and Path(os.environ['LOCALAPPDATA']) / 'Programs' / 'Python',
                 os.getenv('ProgramFiles') and Path(os.environ['ProgramFiles']),
                 Path('C:/')]
        for root in filter(None, roots):
            try:
                for d in sorted(root.glob('Python3*'), reverse=True):
                    if (d / 'python.exe').is_file():
                        c.append([str(d / 'python.exe')])
            except OSError:
                pass
    return c


def find_python(candidates=None, probe=probe_python):
    """Лучший подходящий интерпретатор: (команда, (major, minor, micro, bits)) или None."""
    found = []
    for cmd in (candidates if candidates is not None else candidate_pythons()):
        v = probe(cmd)
        if v and v[:2] >= MIN_PY and v[3] == 64:
            found.append((cmd, v))
    if not found:
        return None

    def rank(item):
        v = item[1][:2]
        return (0, PREFERRED.index(v)) if v in PREFERRED else (1, -v[0] * 100 - v[1])
    return min(found, key=rank)


# ==================== БИБЛИОТЕКИ ====================
def parse_requirements(text):
    out = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            out.append(line)
    return out


def req_stamp(req_text, py_ver) -> str:
    h = hashlib.sha256(('\n'.join(parse_requirements(req_text)) + f'|py{py_ver[0]}.{py_ver[1]}').encode()).hexdigest()
    return h[:32]


def is_critical(req_line) -> bool:
    name = re.split(r'[<>=!~\[; ]', req_line, 1)[0].strip().lower().replace('_', '-')
    return name in CRITICAL


def ensure_venv(py_cmd, py_ver, paths, log):
    vpy = paths.venv_python()
    if vpy.exists():
        v = probe_python([vpy])
        if v and v[:2] == tuple(py_ver[:2]):
            return vpy
        log('окружение повреждено или от другой версии Python — пересоздаю')
        shutil.rmtree(paths.venv, ignore_errors=True)
    paths.tool.mkdir(parents=True, exist_ok=True)
    log('создаю изолированное окружение (venv)…')
    if run_stream(list(py_cmd) + ['-m', 'venv', paths.venv], log) != 0 or not vpy.exists():
        raise SetupError('Не удалось создать окружение Python (venv).\n'
                         'Установите Python с python.org (с галочкой «tcl/tk and IDLE» и «py launcher») и запустите снова.')
    return vpy


def needs_install(vpy, req_text, py_ver, paths) -> bool:
    try:
        if paths.stamp.read_text('utf-8').strip() != req_stamp(req_text, py_ver):
            return True
    except OSError:
        return True
    return probe_import(vpy) is False


def probe_import(vpy) -> bool:
    try:
        r = subprocess.run([str(vpy), '-c', IMPORT_CHECK], capture_output=True, timeout=60,
                           creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL, env=clean_env())
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install_requirements(vpy, req_file, req_text, py_ver, paths, log, runner=run_stream):
    """Ставит библиотеки; возвращает список НЕобязательных пакетов, которые не встали. Критичный сбой — SetupError."""
    base = [vpy, '-m', 'pip', 'install', '--progress-bar', 'off', '--disable-pip-version-check']
    log('обновляю pip…')
    runner(base + ['--upgrade', 'pip'], log)
    log('ставлю библиотеки (первый запуск — несколько минут, это разовая операция)…')
    failed = []
    if runner(base + ['-r', req_file], log) != 0:
        log('пакетная установка не удалась — ставлю по одной, чтобы понять, что именно не встаёт…')
        for line in parse_requirements(req_text):
            if runner(base + [line], log) != 0:
                failed.append(line)
        crit = [x for x in failed if is_critical(x)]
        if crit:
            raise SetupError('Не удалось установить обязательные библиотеки: ' + ', '.join(crit) +
                             '\nПроверьте интернет/прокси и запустите снова. Подробности — в окне ниже и в launcher.log.')
    paths.tool.mkdir(parents=True, exist_ok=True)
    paths.stamp.write_text(req_stamp(req_text, py_ver), 'utf-8')
    return failed


def install_python_via_winget(log) -> bool:
    if not shutil.which('winget'):
        return False
    rc = run_stream(['winget', 'install', '-e', '--id', WINGET_ID, '--scope', 'user', '--silent',
                     '--accept-package-agreements', '--accept-source-agreements'], log, timeout=900)
    return rc == 0


PYTHON_DIRECT = ('3.12.8', 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe')


def install_python_direct(log) -> bool:
    """Запасной путь без winget: официальный установщик python.org, подпись PSF проверяется через Authenticode."""
    if not WIN:
        return False
    import tempfile
    import urllib.request
    ver, url = PYTHON_DIRECT
    dst = Path(tempfile.gettempdir()) / f'python-{ver}-amd64.exe'
    try:
        log(f'скачиваю Python {ver} с python.org...')
        with urllib.request.urlopen(url, timeout=60) as r, open(dst, 'wb') as f:
            shutil.copyfileobj(r, f)
        check = subprocess.run(['powershell', '-NoProfile', '-Command',
                                f"$s=Get-AuthenticodeSignature '{dst}'; if($s.Status -eq 'Valid' -and $s.SignerCertificate.Subject -match 'Python Software Foundation'){{exit 0}}else{{exit 2}}"],
                               capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=60)
        if check.returncode != 0:
            log('подпись установщика не совпала — установка отменена')
            return False
        log('подпись проверена, устанавливаю Python (1–2 минуты)...')
        rc = run_stream([str(dst), '/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1', 'Include_tcltk=1',
                         'Include_test=0', 'Include_doc=0', 'Shortcuts=0'], log, timeout=900)
        return rc == 0
    except Exception as ex:
        log(f'не удалось: {ex}')
        return False
    finally:
        dst.unlink(missing_ok=True)


def prepare(paths, log, confirm):
    """Всё, что нужно до запуска. confirm(text) -> bool спрашивает пользователя. Возвращает (venv_python, project_dir, warnings)."""
    project = paths.project()
    if project is None:
        raise SetupError(f'Не найден main.py острова.\nПоложите лаунчер в папку Island (рядом с main.py). Искал в: {paths.base}')
    req_file = project / 'requirements.txt'
    req_text = req_file.read_text('utf-8') if req_file.is_file() else ''
    found = find_python()
    if not found:
        log('Python 3.10+ (64-бит) не найден.')
        if confirm('Python не найден. Установить автоматически (winget или официальный установщик python.org)?\n'
                   'Права администратора не нужны. Если откажетесь, откроется страница загрузки python.org.') and (
                install_python_via_winget(log) or install_python_direct(log)):
            found = find_python()
        if not found:
            try:
                webbrowser.open(PYTHON_URL)
            except Exception:
                pass
            raise SetupError('Установите Python 3.13 (64-бит) с python.org — на первой странице установщика отметьте «Add python.exe to PATH» —\n'
                             'и запустите лаунчер снова.')
    py_cmd, py_ver = found
    log(f'Python {py_ver[0]}.{py_ver[1]}.{py_ver[2]}: {" ".join(map(str, py_cmd))}')
    vpy = ensure_venv(py_cmd, py_ver, paths, log)
    warns = []
    if needs_install(vpy, req_text, py_ver, paths):
        failed = install_requirements(vpy, project / 'requirements.txt', req_text, py_ver, paths, log)
        if failed:
            warns.append('Не установились необязательные пакеты: ' + ', '.join(failed) + '\nСоответствующие функции будут недоступны.')
    else:
        log('библиотеки уже установлены')
    return vpy, project, warns


# ==================== ЗАПУСК И ОТЧЁТ О СБОЕ ====================
_EXIT_NAMES = {
    0xC0000005: 'нарушение доступа к памяти (access violation)', 0xC0000409: 'повреждение стека/кучи (stack buffer overrun)',
    0xC00000FD: 'переполнение стека', 0xC0000374: 'повреждение кучи (heap corruption)', 0xC000013A: 'прервано (Ctrl+C)',
    0xC0000135: 'не найдена DLL', 0xC0000142: 'ошибка инициализации DLL', 0x40010004: 'процесс завершён',
}


def describe_exit(code: int) -> str:
    u = code & 0xFFFFFFFF
    name = _EXIT_NAMES.get(u)
    return f'{code} (0x{u:08X}' + (f' — {name})' if name else ')') if (code < 0 or code > 255) else str(code)


def file_size(p: Path) -> int:
    try:
        return p.stat().st_size
    except OSError:
        return 0


# ==================== ИЗДАТЕЛЬ В ДИСПЕТЧЕРЕ ЗАДАЧ ====================
# «Издатель» / «Описание» диспетчер задач берёт из версионной информации exe (CompanyName, FileDescription), а при наличии
# цифровой подписи — из сертификата. Подписи у нас нет, поэтому пишем строки в ресурс VERSIONINFO.
def _vs_block(key: str, value: bytes = b'', vtype: int = 1, children=(), vlen: int = 0) -> bytes:
    """Один блок VS_VERSIONINFO: [wLength, wValueLength, wType, szKey, pad, Value, pad, Children]."""
    head = struct.pack('<HHH', 0, vlen, vtype) + key.encode('utf-16-le') + b'\0\0'
    head += b'\0' * (-len(head) % 4)
    body = head + value
    for c in children:
        body += b'\0' * (-len(body) % 4) + c
    return struct.pack('<H', len(body)) + body[2:]


def build_version_info(company=PUBLISHER, product=APP, description=APP, version=APP_VERSION, filename=BRAND_EXE) -> bytes:
    """Готовый ресурс RT_VERSION (английский США, Unicode)."""
    ms, ls = (version[0] << 16) | version[1], (version[2] << 16) | version[3]
    ver = '.'.join(str(x) for x in version)
    fixed = struct.pack('<13I', 0xFEEF04BD, 0x00010000, ms, ls, ms, ls, 0x3F, 0, 0x00040004, 1, 0, 0, 0)
    strings = {'CompanyName': company, 'FileDescription': description, 'FileVersion': ver,
               'InternalName': 'IslandPro', 'LegalCopyright': f'© {company}', 'OriginalFilename': filename,
               'ProductName': product, 'ProductVersion': ver}
    entries = [_vs_block(k, (v + '\0').encode('utf-16-le'), 1, vlen=len(v) + 1) for k, v in strings.items()]
    table = _vs_block('040904B0', b'', 1, entries)
    sfi = _vs_block('StringFileInfo', b'', 1, [table])
    var = _vs_block('Translation', struct.pack('<I', 0x04B00409), 0, vlen=4)
    vfi = _vs_block('VarFileInfo', b'', 1, [var])
    return _vs_block('VS_VERSION_INFO', fixed, 0, [sfi, vfi], vlen=len(fixed))


def read_version_strings(blob: bytes) -> dict:
    """Обратный разбор build_version_info (для проверки): {имя: значение} из StringTable."""
    out = {}
    text = blob.decode('utf-16-le', errors='ignore')
    for k in ('CompanyName', 'FileDescription', 'ProductName', 'OriginalFilename', 'LegalCopyright'):
        i = text.find(k + '\0')
        if i >= 0:
            j = i + len(k) + 1
            while j < len(text) and text[j] == '\0':
                j += 1
            out[k] = text[j:text.find('\0', j)]
    return out


def apply_version_resource(exe: Path, blob: bytes) -> bool:
    """Записывает ресурс версии в exe (kernel32.UpdateResourceW). Только Windows."""
    if not WIN:
        return False
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.BeginUpdateResourceW.restype = wintypes.HANDLE
    k.BeginUpdateResourceW.argtypes = (wintypes.LPCWSTR, wintypes.BOOL)
    k.UpdateResourceW.restype = wintypes.BOOL
    k.UpdateResourceW.argtypes = (wintypes.HANDLE, wintypes.LPVOID, wintypes.LPVOID, wintypes.WORD, wintypes.LPVOID, wintypes.DWORD)
    k.EndUpdateResourceW.restype = wintypes.BOOL
    k.EndUpdateResourceW.argtypes = (wintypes.HANDLE, wintypes.BOOL)
    h = k.BeginUpdateResourceW(str(exe), False)
    if not h:
        return False
    buf = ctypes.create_string_buffer(blob, len(blob))
    ok = k.UpdateResourceW(h, ctypes.c_void_p(16), ctypes.c_void_p(1), 0x0409, buf, len(blob))      # RT_VERSION, id 1, en-US
    return bool(k.EndUpdateResourceW(h, not ok)) and bool(ok)


def branded_python(vpy: Path, paths, log=lambda s: None) -> Path:
    """Копия venv\\Scripts\\python.exe под именем IslandPro.exe с издателем OlegBFF в версионной информации.
    Любая неудача → обычный python.exe (остров просто покажется в диспетчере как «Python»)."""
    if not WIN:
        return vpy
    try:
        dst = vpy.with_name(BRAND_EXE)
        blob = build_version_info()
        stamp = dst.with_name(BRAND_EXE + '.brand')
        tag = hashlib.sha256(blob).hexdigest()[:16] + f'|{vpy.stat().st_size}'
        if dst.exists() and stamp.exists() and stamp.read_text('utf-8').strip() == tag:
            return dst
        tmp = dst.with_name(BRAND_EXE + '.tmp')
        shutil.copy2(vpy, tmp)
        if not apply_version_resource(tmp, blob):
            raise OSError('UpdateResource не удался')
        probe = subprocess.run([str(tmp), '-c', 'import sys'], capture_output=True, timeout=30,
                               creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL, env=clean_env())
        if probe.returncode != 0:
            raise OSError(f'копия не запускается (код {probe.returncode})')
        os.replace(tmp, dst)
        stamp.write_text(tag, 'utf-8')
        log(f'издатель в диспетчере задач: {PUBLISHER} ({BRAND_EXE})')
        return dst
    except Exception as ex:                                     # брендирование — украшение, оно не должно мешать запуску
        log(f'брендирование exe пропущено: {ex!r}')
        try:
            vpy.with_name(BRAND_EXE + '.tmp').unlink()
        except OSError:
            pass
        return vpy


def read_since(p: Path, offset: int, max_lines=60) -> str:
    """Текст файла, дописанный после offset (если файл обрезали — целиком), последние max_lines строк."""
    try:
        with p.open('rb') as f:
            size = f.seek(0, 2)
            f.seek(offset if offset <= size else 0)
            data = f.read().decode('utf-8', errors='replace')
    except OSError:
        return ''
    lines = [ln for ln in data.splitlines() if ln.strip()]
    if len(lines) > max_lines:
        lines = [f'… (пропущено {len(lines) - max_lines} строк)'] + lines[-max_lines:]
    return '\n'.join(lines)


class Run:
    """Один запуск острова: stdout+stderr процесса идут в run.log."""

    def __init__(s, paths, vpy, project, launcher_cmd=''):
        s.paths, s.vpy, s.project, s.launcher_cmd = paths, vpy, project, launcher_cmd
        s.proc = None
        s.t0 = 0.0
        s.offsets = {}

    def start(s):
        pa = s.paths
        pa.data.mkdir(parents=True, exist_ok=True)
        if file_size(pa.run_log) > 1_000_000:
            pa.run_log.write_text('', 'utf-8')
        s.offsets = {p: file_size(p) for p in (pa.run_log, pa.island_log, pa.crash_log)}
        s.t0 = time.time()
        f = pa.run_log.open('a', encoding='utf-8', errors='replace')
        f.write(f'\n===== запуск {time.strftime("%Y-%m-%d %H:%M:%S")} =====\n')
        f.flush()
        env = clean_env({'ISLAND_LAUNCHER_CMD': s.launcher_cmd} if s.launcher_cmd else None)
        try:
            exe = branded_python(s.vpy, pa, lambda t: f.write(f'[launcher] {t}\n'))
            s.proc = subprocess.Popen([str(exe), '-X', 'faulthandler', '-u', str(s.project / 'main.py')], cwd=str(s.project),
                                      env=env, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT,
                                      creationflags=CREATE_NO_WINDOW)
        finally:
            f.close()                                   # у процесса своя копия дескриптора
        return s

    def wait(s) -> int:
        return s.proc.wait()

    def report(s, code: int) -> str:
        pa = s.paths
        sections = [('Вывод процесса (run.log)', pa.run_log, 60), ('Журнал острова (island.log)', pa.island_log, 60),
                    ('Нативные падения (crash.log)', pa.crash_log, 60)]
        out = [f'=== {APP}: сбой ===', f'Время: {time.strftime("%Y-%m-%d %H:%M:%S")}',
               f'Работал: {time.time() - s.t0:.0f} с', f'Код выхода: {describe_exit(code)}', f'Папка логов: {pa.data}']
        for title, path, n in sections:
            body = read_since(path, s.offsets.get(path, 0), n)
            if body:
                out += ['', f'--- {title} ---', body]
        return '\n'.join(out)

    @staticmethod
    def has_details(report: str) -> bool:
        return '--- ' in report


def should_report(code: int, report: str) -> bool:
    """Тихий выход: код 0 (штатно, «Выход» в трее, второй экземпляр) или код 1 без единой строки лога
    (так выглядит процесс, снятый в диспетчере задач). Любой другой код без логов — тоже сбой (нативное падение)."""
    return code != 0 and (Run.has_details(report) or code != 1)


class RestartPolicy:
    def __init__(s, limit=CRASH_LOOP[0], window=CRASH_LOOP[1]):
        s.limit, s.window, s.times = limit, window, []

    def record(s, now=None):
        now = time.time() if now is None else now
        s.times = [t for t in s.times if now - t < s.window] + [now]

    def allow_auto(s) -> bool:
        return len(s.times) < s.limit


def load_settings(paths) -> dict:
    try:
        return json.loads(paths.settings.read_text('utf-8'))
    except (OSError, ValueError):
        return {}


def save_settings(paths, data: dict):
    try:
        paths.tool.mkdir(parents=True, exist_ok=True)
        paths.settings.write_text(json.dumps(data), 'utf-8')
    except OSError:
        pass


def launcher_command() -> str:
    """Команда, которой Windows будет запускать лаунчер при автозапуске."""
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    exe = sys.executable
    if WIN and exe.lower().endswith('python.exe'):
        pw = exe[:-10] + 'pythonw.exe'
        exe = pw if os.path.exists(pw) else exe
    return f'"{exe}" "{Path(__file__).resolve()}"'


# ==================== ОКНО (tkinter) ====================
BG, FG, MUTED, ACC, ERR = '#16161a', '#f2f2f5', '#8e8e93', '#0a84ff', '#ff453a'


class App:
    """Тонкая оболочка: всё содержательное — в функциях выше. Рабочий поток шлёт сообщения в очередь, окно их разбирает."""

    def __init__(s, paths=None):
        import tkinter as tk
        from tkinter import ttk
        s.tk, s.ttk = tk, ttk
        s.paths = paths or Paths()
        s.q = queue.Queue()
        s.decisions = queue.Queue()
        s.answer = queue.Queue()
        s.root = tk.Tk()
        s.root.title(f'{APP} — запуск')
        s.root.geometry('760x460')
        s.root.configure(bg=BG)
        s.root.protocol('WM_DELETE_WINDOW', s.quit_all)
        s.log_lines = []
        s.closing = False
        s.status = tk.StringVar(value='Подготовка…')
        tk.Label(s.root, textvariable=s.status, bg=BG, fg=FG, font=('Segoe UI', 12, 'bold'), anchor='w',
                 wraplength=720, justify='left').pack(fill='x', padx=16, pady=(14, 6))
        s.bar = ttk.Progressbar(s.root, mode='indeterminate')
        s.bar.pack(fill='x', padx=16)
        s.text = tk.Text(s.root, bg='#0e0e10', fg='#d0d0d6', insertbackground=FG, relief='flat', font=('Consolas', 9),
                         wrap='word', state='disabled', height=14)
        s.text.pack(fill='both', expand=True, padx=16, pady=10)
        s.text.tag_configure('err', foreground=ERR)
        s.buttons = tk.Frame(s.root, bg=BG)
        s.buttons.pack(fill='x', padx=16, pady=(0, 14))
        s.root.withdraw()
        s.root.after(80, s.pump)

    # ---- вызывается из рабочего потока ----
    def post(s, *msg):
        s.q.put(msg)

    def log(s, line):
        s.log_lines.append(line)
        try:
            s.paths.data.mkdir(parents=True, exist_ok=True)
            with s.paths.launcher_log.open('a', encoding='utf-8') as f:
                f.write(f'[{time.strftime("%H:%M:%S")}] {line}\n')
        except OSError:
            pass
        s.post('log', line)

    def confirm(s, text) -> bool:
        s.post('show')
        s.post('ask', text)
        return s.answer.get()

    # ---- главный поток ----
    def pump(s):
        try:
            while True:
                kind, *a = s.q.get_nowait()
                getattr(s, 'on_' + kind)(*a)
        except queue.Empty:
            pass
        if not s.closing:
            s.root.after(80, s.pump)

    def on_log(s, line):
        s.text.configure(state='normal')
        s.text.insert('end', line + '\n', 'err' if re.search(r'(?i)\berror\b|ошибк|failed|не удалось', line) else ())
        s.text.see('end')
        s.text.configure(state='disabled')

    def on_status(s, text):
        s.status.set(text)

    def on_show(s):
        s.root.deiconify()
        s.root.lift()
        s.bar.start(12)

    def on_hide(s):
        s.bar.stop()
        s.root.withdraw()

    def on_quit(s):
        s.closing = True
        s.root.destroy()

    def clear_buttons(s):
        for w in s.buttons.winfo_children():
            w.destroy()

    def add_button(s, text, cmd, primary=False):
        b = s.tk.Button(s.buttons, text=text, command=cmd, relief='flat', padx=14, pady=6, cursor='hand2',
                        bg=ACC if primary else '#2c2c30', fg=FG, activebackground='#3a3a40', activeforeground=FG)
        b.pack(side='left', padx=(0, 8))
        return b

    def on_ask(s, text):
        s.clear_buttons()
        s.status.set(text)
        s.bar.stop()

        def pick(v):
            s.clear_buttons()
            s.bar.start(12)
            s.answer.put(v)
        s.add_button('Да, установить', lambda: pick(True), True)
        s.add_button('Нет', lambda: pick(False))

    def copy(s, text):
        s.root.clipboard_clear()
        s.root.clipboard_append(text)
        s.root.update()

    def open_logs(s):
        try:
            os.startfile(str(s.paths.data))
        except (AttributeError, OSError):
            webbrowser.open(s.paths.data.as_uri())

    def on_error(s, title, text):
        """Сбой подготовки: окно остаётся, лог можно скопировать, попробовать ещё раз."""
        s.bar.stop()
        s.root.deiconify()
        s.status.set(title)
        s.on_log('')
        s.on_log(text)
        s.clear_buttons()
        full = '\n'.join([title, text, '', *s.log_lines])
        s.add_button('Повторить', s.retry, True)
        s.add_button('Копировать лог', lambda: s.copy(full))
        s.add_button('Открыть папку логов', s.open_logs)
        s.add_button('Закрыть', s.quit_all)

    def retry(s):
        s.clear_buttons()
        s.status.set('Подготовка…')
        s.bar.start(12)
        threading.Thread(target=s.boot, daemon=True).start()

    def on_crash(s, report, auto):
        s.bar.stop()
        win = s.tk.Toplevel(s.root)
        win.title(f'{APP} — остров завершился с ошибкой')
        win.geometry('820x560')
        win.configure(bg=BG)
        win.attributes('-topmost', True)
        s.tk.Label(win, text='Остров вылетел. Вот что удалось выяснить:', bg=BG, fg=FG, font=('Segoe UI', 12, 'bold'),
                   anchor='w').pack(fill='x', padx=16, pady=(14, 6))
        box = s.tk.Text(win, bg='#0e0e10', fg='#d0d0d6', relief='flat', font=('Consolas', 9), wrap='none')
        box.insert('1.0', report)
        box.configure(state='disabled')
        box.pack(fill='both', expand=True, padx=16, pady=6)
        row = s.tk.Frame(win, bg=BG)
        row.pack(fill='x', padx=16, pady=(0, 14))
        done = {'v': False}
        countdown = s.tk.StringVar(value='')
        auto_var = s.tk.BooleanVar(value=bool(load_settings(s.paths).get('auto_restart')))

        def decide(v):
            if done['v']:
                return
            done['v'] = True
            save_settings(s.paths, {**load_settings(s.paths), 'auto_restart': bool(auto_var.get())})
            win.destroy()
            s.decisions.put(v)

        def tick(n):
            if done['v']:
                return
            if not auto_var.get():
                countdown.set('')
                win.after(500, tick, AUTO_RESTART_DELAY)
                return
            if not auto:
                countdown.set('Слишком частые сбои — автоперезапуск остановлен.')
                win.after(500, tick, AUTO_RESTART_DELAY)
                return
            if n <= 0:
                decide('restart')
                return
            countdown.set(f'Перезапуск через {n} с…')
            win.after(1000, tick, n - 1)

        b = lambda t, c, p=False: s.tk.Button(row, text=t, command=c, relief='flat', padx=14, pady=6, cursor='hand2',
                                              bg=ACC if p else '#2c2c30', fg=FG, activebackground='#3a3a40',
                                              activeforeground=FG).pack(side='left', padx=(0, 8))
        b('Перезапустить', lambda: decide('restart'), True)
        b('Копировать', lambda: s.copy(report))
        b('Папка логов', s.open_logs)
        b('Закрыть', lambda: decide('quit'))
        s.tk.Checkbutton(row, text='Перезапускать автоматически', variable=auto_var, bg=BG, fg=FG, selectcolor='#2c2c30',
                         activebackground=BG, activeforeground=FG).pack(side='left', padx=8)
        s.tk.Label(row, textvariable=countdown, bg=BG, fg=MUTED).pack(side='left')
        win.protocol('WM_DELETE_WINDOW', lambda: decide('quit'))
        tick(AUTO_RESTART_DELAY)

    def quit_all(s):
        s.decisions.put('quit')
        s.answer.put(False)
        if not s.closing:
            s.closing = True
            s.root.destroy()

    # ---- рабочий поток ----
    def boot(s):
        try:
            vpy, project, warns = prepare(s.paths, s.log, s.confirm)
        except SetupError as ex:
            s.post('error', 'Не удалось подготовить окружение', str(ex))
            return
        except Exception:
            s.post('error', 'Непредвиденная ошибка лаунчера', traceback.format_exc())
            return
        if warns:
            s.post('show')
            for w in warns:
                s.log(w)
            time.sleep(4)
        s.post('status', 'Запускаю остров…')
        s.post('hide')
        try:
            s.supervise(vpy, project)
        except Exception:
            s.post('error', 'Не удалось запустить остров', traceback.format_exc())

    def supervise(s, vpy, project):
        policy = RestartPolicy()
        while True:
            run = Run(s.paths, vpy, project, launcher_command()).start()
            code = run.wait()
            report = run.report(code)
            if not should_report(code, report):
                s.post('quit')
                return
            policy.record()
            try:
                s.paths.last_crash.write_text(report, 'utf-8')
            except OSError:
                pass
            s.post('crash', report, policy.allow_auto())
            if s.decisions.get() != 'restart':
                s.post('quit')
                return

    def run(s):
        threading.Thread(target=s.boot, daemon=True).start()
        s.root.mainloop()


def single_instance() -> bool:
    if not WIN:
        return True
    try:
        import ctypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        single_instance.handle = k32.CreateMutexW(None, False, 'Local\\IslandPro.Launcher')
        return ctypes.get_last_error() != 183
    except Exception:
        return True


def fatal_box(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text[-1500:], f'{APP} — лаунчер', 0x10)
    except Exception:
        if sys.stderr:
            sys.stderr.write(text)


def main():
    if not single_instance():
        return
    if WIN:
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    try:
        App().run()
    except Exception:
        text = traceback.format_exc()
        try:
            p = Paths()
            p.data.mkdir(parents=True, exist_ok=True)
            with p.launcher_log.open('a', encoding='utf-8') as f:
                f.write(text)
        except OSError:
            pass
        fatal_box('Лаунчер не смог запуститься:\n\n' + text)


if __name__ == '__main__':
    main()
