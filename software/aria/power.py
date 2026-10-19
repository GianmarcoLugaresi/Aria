"""Batteria e schermo del Mac, letti senza programmi esterni (ctypes su IOKit e CoreGraphics).

Serve al risparmio energetico: il microfono sempre aperto (per sentire «hey aria») tiene sveglio il Mac, che con il microfono acceso non va mai in stop da solo
(macOS lo segnala come «PreventUserIdleSystemSleep» di coreaudiod per il microfono). A batteria e con lo schermo spento Aria smette di ascoltare e lascia dormire il Mac."""
from __future__ import annotations

import ctypes
import sys

_iokit = None
_cg = None


class _SystemPowerStatus(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte), ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                ("BatteryLifeTime", ctypes.c_uint32), ("BatteryFullLifeTime", ctypes.c_uint32)]


def _win_on_battery() -> bool | None:
    """Windows: GetSystemPowerStatus. ACLineStatus 0 = a batteria, 1 = alimentatore, 255 = non si sa. Un PC fisso senza batteria (BatteryFlag 128) conta come alimentatore."""
    try:
        st = _SystemPowerStatus()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):             # type: ignore[attr-defined]
            return None
    except Exception:                                                     # noqa: BLE001
        return None
    if st.BatteryFlag == 128:
        return False
    return {0: True, 1: False}.get(st.ACLineStatus)


def on_battery() -> bool | None:
    """True = il computer va a batteria, False = e' collegato all'alimentatore, None = non si sa (altri sistemi, errore)."""
    global _iokit
    if sys.platform == "win32":
        return _win_on_battery()
    if sys.platform != "darwin":
        return None
    try:
        if _iokit is None:
            _iokit = ctypes.CDLL("/System/Library/Frameworks/IOKit.framework/IOKit")
            _iokit.IOPSGetTimeRemainingEstimate.restype = ctypes.c_double
        t = float(_iokit.IOPSGetTimeRemainingEstimate())
    except Exception:                                                     # noqa: BLE001
        return None
    return t != -2.0                                                      # -2 = kIOPSTimeRemainingUnlimited: alimentatore; -1 = a batteria, stima in corso; >0 = a batteria


def display_asleep() -> bool | None:
    """True = lo schermo principale e' spento (sleep del display), None = non si sa (su Windows non c'e' una domanda semplice da fare: sempre None)."""
    global _cg
    if sys.platform != "darwin":
        return None
    try:
        if _cg is None:
            _cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            _cg.CGMainDisplayID.restype = ctypes.c_uint32
            _cg.CGDisplayIsAsleep.argtypes = [ctypes.c_uint32]
            _cg.CGDisplayIsAsleep.restype = ctypes.c_bool
        return bool(_cg.CGDisplayIsAsleep(_cg.CGMainDisplayID()))
    except Exception:                                                     # noqa: BLE001
        return None
