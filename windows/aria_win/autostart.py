"""«Avvia con Windows»: una voce nella chiave Run dell'utente (nessun permesso da amministratore)."""
from __future__ import annotations

import sys

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Aria"


def command() -> str:
    from . import paths
    return f'"{paths.python_exe(windowless=True)}" -m aria_win'


def _reg(reg=None):
    if reg is not None:
        return reg
    import winreg
    return winreg


def is_enabled(reg=None) -> bool:
    if reg is None and sys.platform != "win32":
        return False
    r = _reg(reg)
    try:
        with r.OpenKey(r.HKEY_CURRENT_USER, KEY, 0, r.KEY_READ) as k:
            r.QueryValueEx(k, NAME)
            return True
    except OSError:
        return False


def set_enabled(on: bool, reg=None) -> bool:
    """Accende o spegne l'avvio automatico. True se ci e' riuscito."""
    if reg is None and sys.platform != "win32":
        return False
    r = _reg(reg)
    try:
        with r.CreateKeyEx(r.HKEY_CURRENT_USER, KEY, 0, r.KEY_SET_VALUE) as k:
            if on:
                r.SetValueEx(k, NAME, 0, r.REG_SZ, command())
            else:
                try:
                    r.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
