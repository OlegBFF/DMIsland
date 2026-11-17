"""Панель «sys»: собственная панель управления системой."""
from ui.control_center import ControlCenter


class SysPanel:
    """Часть класса Island: SysPanel."""

    def pg_sys(s):
        s.cc = ControlCenter(s)
        return s.cc
