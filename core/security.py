"""Безопасность: DPAPI-шифрование ключей, безопасный eval, ограниченный HTTP, безопасное открытие путей."""
import ast
import base64
import ctypes
import os
import re
import ssl
import threading
import ctypes.wintypes
import urllib.parse
import urllib.request
from pathlib import Path
from core.constants import MAX_HTTP_BYTES, MAX_STREAM_BYTES


# ==================== МОДУЛЬ КИБЕРБЕЗОПАСНОСТИ (DPAPI, AST, SAFE URL/SSL) ====================
class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', ctypes.wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def dpapi_encrypt(plain_text: str) -> str:
    """Шифрует секретную строку (API-ключ) через системный Windows DPAPI текущего пользователя."""
    if not plain_text:
        return ''
    try:
        raw = plain_text.encode('utf-8')
        buf = ctypes.create_string_buffer(raw, len(raw))
        blob_in = DATA_BLOB(len(raw), buf)
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptProtectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
            enc = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return base64.b64encode(enc).decode('ascii')
    except Exception:
        pass
    return ''


def dpapi_decrypt(b64_text: str) -> str:
    """Расшифровывает строку через Windows DPAPI (работает только под тем же пользователем Windows)."""
    if not b64_text:
        return ''
    try:
        raw = base64.b64decode(b64_text.encode('ascii'))
        buf = ctypes.create_string_buffer(raw, len(raw))
        blob_in = DATA_BLOB(len(raw), buf)
        blob_out = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
            dec = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
            return dec.decode('utf-8', 'ignore')
    except Exception:
        pass
    return ''


def safe_math_eval(expr: str) -> str:
    """Безопасное вычисление математических выражений через AST без использования eval()."""
    if len(expr) > 80:
        raise ValueError("Слишком длинное выражение")
    allowed_ops = {
        ast.Add: lambda a, b: a + b,
        ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b,
        ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b,
        ast.Mod: lambda a, b: a % b,
        ast.Pow: lambda a, b: a ** b if abs(b) <= 100 and abs(a) <= 100000 else (_ for _ in ()).throw(ValueError("Overflow")),
    }
    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = _eval(node.operand)
            return +v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](_eval(node.left), _eval(node.right))
        raise ValueError("Недопустимая операция")

    val = _eval(ast.parse(expr.strip(), mode='eval'))
    return str(round(val, 6)).rstrip('0').rstrip('.') if isinstance(val, float) else str(val)


_SSL_CTX = None
_SSL_LOCK = threading.Lock()


def ssl_context():
    """Один общий SSL-контекст. ssl.create_default_context() при каждом запросе заново читает хранилище сертификатов
    Windows (сотни COM/CryptoAPI-вызовов, десятки мс, куча временных объектов) — именно там сборщик мусора
    ловил чужие битые COM-указатели. Контекст потокобезопасен для чтения, создаём его один раз."""
    global _SSL_CTX
    if _SSL_CTX is None:
        with _SSL_LOCK:
            if _SSL_CTX is None:
                _SSL_CTX = ssl.create_default_context()
    return _SSL_CTX


def safe_urlopen(url: str, data=None, headers=None, timeout=10) -> bytes:
    """Безопасный HTTPS-запрос с проверкой сертификата, защитой от SSRF/file:// и лимитом размера."""
    parsed = urllib.parse.urlparse(url)
    is_local_http = parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')
    if parsed.scheme != 'https' and not is_local_http:
        raise ValueError(f"Заблокирована небезопасная схема URL: {parsed.scheme}")
    req = urllib.request.Request(url, data=data, headers=headers or {'User-Agent': 'IslandPro/5.4'})
    ctx = ssl_context() if parsed.scheme == 'https' else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read(MAX_HTTP_BYTES)


def safe_urlopen_stream(url: str, data=None, headers=None, timeout=30):
    """Как safe_urlopen, но возвращает открытый ответ для построчного чтения (SSE). Закрывать должен вызывающий."""
    parsed = urllib.parse.urlparse(url)
    is_local_http = parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost')
    if parsed.scheme != 'https' and not is_local_http:
        raise ValueError(f"Заблокирована небезопасная схема URL: {parsed.scheme}")
    req = urllib.request.Request(url, data=data, headers=headers or {'User-Agent': 'IslandPro/5.4'})
    ctx = ssl_context() if parsed.scheme == 'https' else None
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def safe_open_path(target: str) -> bool:
    """Безопасное открытие файлов и ссылок с блокировкой UNC-путей (\\server) и опасных URI-схем."""
    t = target.strip()
    if not t or t.startswith('\\\\') or t.startswith('//'):
        return False
    parsed = urllib.parse.urlparse(t)
    if parsed.scheme in ('https', 'http'):
        os.startfile(t)
        return True
    if parsed.scheme == 'steam' and re.match(r'^steam://(run|rungameid)/\d+$', t):
        os.startfile(t)
        return True
    p = Path(t)
    if p.exists() and not str(p).startswith('\\\\'):
        os.startfile(str(p.resolve()))
        return True
    return False
