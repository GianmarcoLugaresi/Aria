"""Informazioni sul Mac (o sul PC Windows) che Aria sa dire a voce: batteria, spazio sul disco, versione di macOS o di Windows, da quanto e' acceso, wifi, indirizzo IP, memoria.
Solo LETTURA: comandi di sistema senza argomenti dell'utente (niente testo detto a voce finisce in un comando)."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import socket
import sys
import time

from . import i18n
from .speech import num_words


async def _run(*cmd: str, timeout: float = 8.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        return out.decode("utf-8", "ignore")
    except Exception:                                                  # noqa: BLE001
        return ""


def _pct(n: int) -> str:
    if i18n.is_en():
        return f"{num_words(n)} percent" if n < 1000 else f"{n} percent"
    return f"{num_words(n)} per cento" if n < 1000 else f"{n} per cento"


def _hm(h: int, m: int) -> str:
    if i18n.is_en():
        parts = []
        if h:
            parts.append("an hour" if h == 1 else f"{num_words(h)} hours")
        if m:
            parts.append("a minute" if m == 1 else f"{num_words(m)} minutes")
        return " and ".join(parts) or "a few minutes"
    parts = []
    if h:
        parts.append("un'ora" if h == 1 else f"{num_words(h)} ore")
    if m:
        parts.append("un minuto" if m == 1 else f"{num_words(m)} minuti")
    return " e ".join(parts) or "pochi minuti"


async def battery() -> str:
    out = await _run("/usr/bin/pmset", "-g", "batt")
    m = re.search(r"(\d{1,3})%;\s*([a-z ]+?)(?:;|\s*\()(?:\s*(\d+):(\d{2}) remaining)?", out)
    if not m:
        if i18n.is_en():
            return "This Mac has no battery." if out and "InternalBattery" not in out else "I can't read the battery."
        return "Questo Mac non ha la batteria." if out and "InternalBattery" not in out else "Non riesco a leggere la batteria."
    pct, state = int(m.group(1)), m.group(2).strip()
    plugged = "AC Power" in out
    if i18n.is_en():
        timed = bool(m.group(3)) and not (m.group(3) == "0" and m.group(4) == "00")
        if "charged" in state or "finishing" in state:
            return f"The battery is fully charged at {_pct(pct)}" + (" and you're plugged in." if plugged else ".")
        if "discharging" in state:
            left = f", about {_hm(int(m.group(3)), int(m.group(4)))} left" if timed else ""
            return f"You have {_pct(pct)} battery and you're not plugged in{left}."
        if "charging" in state:
            left = f", about {_hm(int(m.group(3)), int(m.group(4)))} to go until it's full" if timed else ""
            return f"You have {_pct(pct)} battery and it's charging{left}."
        return f"You have {_pct(pct)} battery."
    if "charged" in state or ("finishing" in state):
        return f"La batteria è carica al {_pct(pct)}" + (" e sei collegato alla corrente." if plugged else ".")
    if "discharging" in state:
        left = f", resta circa {_hm(int(m.group(3)), int(m.group(4)))}" if m.group(3) and not (m.group(3) == "0" and m.group(4) == "00") else ""
        return f"Hai il {_pct(pct)} di batteria, non sei collegato alla corrente{left}."
    if "charging" in state:
        left = f", mancano circa {_hm(int(m.group(3)), int(m.group(4)))} per averla piena" if m.group(3) and not (m.group(3) == "0" and m.group(4) == "00") else ""
        return f"Hai il {_pct(pct)} di batteria e si sta caricando{left}."
    return f"Hai il {_pct(pct)} di batteria."


async def disk() -> str:
    total, used, free = shutil.disk_usage("/System/Volumes/Data" if shutil.os.path.exists("/System/Volumes/Data") else "/")
    gb = lambda n: round(n / 1e9)
    if i18n.is_en():
        return f"You have about {num_words(gb(free))} gigabytes free out of {num_words(gb(total))}."
    return f"Hai circa {num_words(gb(free))} giga liberi su {num_words(gb(total))}."


async def version() -> str:
    v = (await _run("/usr/bin/sw_vers", "-productVersion")).strip()
    if i18n.is_en():
        return f"You have macOS {v.replace('.', ' point ')}." if v else "I can't read the macOS version."
    return f"Hai macOS {v.replace('.', ' punto ')}." if v else "Non riesco a leggere la versione di macOS."             # («15.4» letto come numero sarebbe «quindici virgola quattro»)


async def uptime() -> str:
    out = await _run("/usr/sbin/sysctl", "-n", "kern.boottime")
    m = re.search(r"sec\s*=\s*(\d+)", out)
    if not m:
        return i18n.pick("Non riesco a leggere da quanto è acceso il Mac.", "I can't read how long the Mac has been on.")
    secs = int(time.time()) - int(m.group(1))
    d, h, mi = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
    if i18n.is_en():
        if d:
            return f"The Mac has been on for {'a day' if d == 1 else num_words(d) + ' days'} and {_hm(h, 0) if h else 'a few hours'}."
        return f"The Mac has been on for {_hm(h, mi)}."
    if d:
        return f"Il Mac è acceso da {'un giorno' if d == 1 else num_words(d) + ' giorni'} e {_hm(h, 0) if h else 'poche ore'}."
    return f"Il Mac è acceso da {_hm(h, mi)}."


async def wifi() -> str:
    out = await _run("/usr/sbin/networksetup", "-getairportnetwork", "en0")
    m = re.search(r"Network:\s*(.+)", out)
    if m and "<redacted>" not in m.group(1):
        return i18n.pick(f"Sei collegato alla rete wifi {m.group(1).strip()}.", f"You're connected to the wifi network {m.group(1).strip()}.")
    ip = (await _run("/usr/sbin/ipconfig", "getifaddr", "en0")).strip()
    if i18n.is_en():
        return "You're connected to wifi, but macOS won't tell me the network's name." if ip else "You don't seem to be connected to wifi."
    return "Sei collegato al wifi, ma macOS non mi dice come si chiama la rete." if ip else "Non risulti collegato al wifi."


async def ip() -> str:
    for ifc in ("en0", "en1"):
        v = (await _run("/usr/sbin/ipconfig", "getifaddr", ifc)).strip()
        if v:
            if i18n.is_en():
                return "Your IP address on the local network is " + " dot ".join(v.split(".")[:4]) + "."
            return "Il tuo indirizzo IP sulla rete locale è " + ", ".join(v.split(".")[:4]).replace(", ", " punto ") + "."
    return i18n.pick("Non risulti collegato a una rete.", "You don't seem to be connected to a network.")


async def memory() -> str:
    out = await _run("/usr/bin/memory_pressure")
    m = re.search(r"free percentage:\s*(\d+)%", out)
    total = int((await _run("/usr/sbin/sysctl", "-n", "hw.memsize")).strip() or 0)
    if i18n.is_en():
        tot = f" of {num_words(round(total / 2**30))} gigabytes" if total else ""
        return f"About {_pct(int(m.group(1)))} of the memory is free{tot}." if m else "I can't read the memory."
    tot = f" su {num_words(round(total / 2**30))} giga" if total else ""
    return f"La memoria libera è circa il {_pct(int(m.group(1)))}{tot}." if m else "Non riesco a leggere la memoria."


KINDS = {"batteria": battery, "spazio": disk, "versione": version, "accensione": uptime, "wifi": wifi, "ip": ip, "memoria": memory}


# ------------------------------------------------------------------------------- Windows (stesse domande, letture di Windows: ctypes e `netsh`, niente di scritto dall'utente)
def _win_power():
    """(percentuale, collegato all'alimentatore, secondi rimasti o None) oppure None se non c'e' batteria / non si legge."""
    import ctypes
    from .power import _SystemPowerStatus
    st = _SystemPowerStatus()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):             # type: ignore[attr-defined]
        raise OSError("GetSystemPowerStatus")
    if st.BatteryFlag == 128 or st.BatteryLifePercent == 255:
        return None
    left = None if st.BatteryLifeTime in (0xFFFFFFFF, 0) else int(st.BatteryLifeTime)
    return int(st.BatteryLifePercent), st.ACLineStatus == 1, left


def _win_memory():
    """(percentuale libera, byte totali)."""
    import ctypes

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32), ("ullTotalPhys", ctypes.c_uint64), ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64), ("ullAvailPageFile", ctypes.c_uint64), ("ullTotalVirtual", ctypes.c_uint64), ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64)]
    st = MemoryStatus()
    st.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):             # type: ignore[attr-defined]
        raise OSError("GlobalMemoryStatusEx")
    return 100 - int(st.dwMemoryLoad), int(st.ullTotalPhys)


def _win_uptime_seconds() -> int:
    import ctypes
    return int(ctypes.windll.kernel32.GetTickCount64() // 1000)                      # type: ignore[attr-defined]


def _win_build() -> int:
    return int(getattr(sys, "getwindowsversion")().build)


def _local_ip() -> str:
    """L'indirizzo di questo PC sulla rete locale: un socket UDP «collegato» a un indirizzo qualunque non spedisce niente, ma dice da quale interfaccia uscirebbe."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]


async def win_battery() -> str:
    try:
        power = _win_power()
    except Exception:                                                  # noqa: BLE001
        return i18n.pick("Non riesco a leggere la batteria.", "I can't read the battery.")
    if power is None:
        return i18n.pick("Questo PC non ha la batteria.", "This PC has no battery.")
    pct, plugged, left = power
    h, m = ((left or 0) // 3600, (left or 0) % 3600 // 60)
    if i18n.is_en():
        if plugged:
            return f"The battery is at {_pct(pct)} and you're plugged in." if pct < 100 else "The battery is fully charged and you're plugged in."
        return f"You have {_pct(pct)} battery and you're not plugged in" + (f", about {_hm(h, m)} left." if left else ".")
    if plugged:
        return f"La batteria è al {_pct(pct)} e sei collegato alla corrente." if pct < 100 else "La batteria è carica e sei collegato alla corrente."
    return f"Hai il {_pct(pct)} di batteria, non sei collegato alla corrente" + (f", resta circa {_hm(h, m)}." if left else ".")


async def win_disk() -> str:
    total, _used, free = shutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\")
    gb = lambda n: round(n / 1e9)
    if i18n.is_en():
        return f"You have about {num_words(gb(free))} gigabytes free out of {num_words(gb(total))}."
    return f"Hai circa {num_words(gb(free))} giga liberi su {num_words(gb(total))}."


async def win_version() -> str:
    try:
        n = 11 if _win_build() >= 22000 else 10
    except Exception:                                                  # noqa: BLE001
        return i18n.pick("Non riesco a leggere la versione di Windows.", "I can't read the Windows version.")
    return i18n.pick(f"Hai Windows {n}.", f"You have Windows {n}.")


async def win_uptime() -> str:
    try:
        secs = _win_uptime_seconds()
    except Exception:                                                  # noqa: BLE001
        return i18n.pick("Non riesco a leggere da quanto è acceso il PC.", "I can't read how long the PC has been on.")
    d, h, mi = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
    if i18n.is_en():
        if d:
            return f"The PC has been on for {'a day' if d == 1 else num_words(d) + ' days'} and {_hm(h, 0) if h else 'a few hours'}."
        return f"The PC has been on for {_hm(h, mi)}."
    if d:
        return f"Il PC è acceso da {'un giorno' if d == 1 else num_words(d) + ' giorni'} e {_hm(h, 0) if h else 'poche ore'}."
    return f"Il PC è acceso da {_hm(h, mi)}."


async def win_wifi() -> str:
    out = await _run("netsh", "wlan", "show", "interfaces")
    m = re.search(r"^\s*SSID\s*:\s*(.+?)\s*$", out, flags=re.M)
    if m:
        return i18n.pick(f"Sei collegato alla rete wifi {m.group(1)}.", f"You're connected to the wifi network {m.group(1)}.")
    return i18n.pick("Non risulti collegato al wifi.", "You don't seem to be connected to wifi.")


async def win_ip() -> str:
    try:
        v = _local_ip()
    except OSError:
        return i18n.pick("Non risulti collegato a una rete.", "You don't seem to be connected to a network.")
    if i18n.is_en():
        return "Your IP address on the local network is " + " dot ".join(v.split(".")[:4]) + "."
    return "Il tuo indirizzo IP sulla rete locale è " + ", ".join(v.split(".")[:4]).replace(", ", " punto ") + "."


async def win_memory() -> str:
    try:
        free, total = _win_memory()
    except Exception:                                                  # noqa: BLE001
        return i18n.pick("Non riesco a leggere la memoria.", "I can't read the memory.")
    if i18n.is_en():
        return f"About {_pct(free)} of the memory is free of {num_words(round(total / 2**30))} gigabytes."
    return f"La memoria libera è circa il {_pct(free)} su {num_words(round(total / 2**30))} giga."


WIN_KINDS = {"batteria": win_battery, "spazio": win_disk, "versione": win_version, "accensione": win_uptime, "wifi": win_wifi, "ip": win_ip, "memoria": win_memory}


async def answer(kind: str) -> str:
    on_windows = sys.platform == "win32"
    fn = (WIN_KINDS if on_windows else KINDS).get(kind.strip().lower())
    if fn:
        return await fn()
    return i18n.pick("Questa informazione sul PC non la so dire.", "I can't tell you that about the PC.") if on_windows else i18n.pick("Questa informazione sul Mac non la so dire.", "I can't tell you that about the Mac.")
