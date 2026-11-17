"""Минимальные заглушки PySide6 — чтобы тестировать логику миксинов без Qt."""
import sys
import types


class D:
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return D()

    def __getattr__(self, n):
        if n.startswith('__'):
            raise AttributeError(n)
        return D()

    def __or__(self, o):
        return self
    __ror__ = __and__ = __or__

    def __iter__(self):
        return iter(())


class Meta(type):
    def __getattr__(cls, n):
        if n.startswith('__'):
            raise AttributeError(n)
        return D()


class Base(metaclass=Meta):
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, n):
        if n.startswith('__'):
            raise AttributeError(n)
        return D()


def _mk(name):
    m = types.ModuleType(name)
    cache = {}

    def ga(n):
        if n.startswith('__'):
            raise AttributeError(n)
        if n not in cache:
            cache[n] = Meta(n, (Base,), {})
        return cache[n]
    m.__getattr__ = ga
    m.__path__ = []
    return m


def install():
    if getattr(sys.modules.get('PySide6'), '_island_stub', False):
        return
    for n in ['PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtNetwork']:
        sys.modules[n] = _mk(n)
    sys.modules['PySide6']._island_stub = True
    sys.modules['PySide6.QtCore'].Signal = lambda *a, **k: D()
    sys.modules['winreg'] = sys.modules.get('winreg') or _mk('winreg')
