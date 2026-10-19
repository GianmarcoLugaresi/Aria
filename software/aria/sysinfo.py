"""Informazioni sul Mac che Aria sa dire a voce: batteria, spazio sul disco, versione di macOS, da quanto e' acceso, wifi, indirizzo IP, memoria.
Solo LETTURA: comandi di sistema senza argomenti dell'utente (niente testo detto a voce finisce in un comando)."""
from __future__ import annotations

import asyncio
import re
import shutil
import time

from .speech import num_words


async def _run(*cmd: str, timeout: float = 8.0) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        return out.decode("utf-8", "ignore")
    except Exception:                                                  # noqa: BLE001
        return ""


def _pct(n: int) -> str:
    return f"{num_words(n)} per cento" if n < 1000 else f"{n} per cento"


def _hm(h: int, m: int) -> str:
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
        return "Questo Mac non ha la batteria." if out and "InternalBattery" not in out else "Non riesco a leggere la batteria."
    pct, state = int(m.group(1)), m.group(2).strip()
    plugged = "AC Power" in out
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
    return f"Hai circa {num_words(gb(free))} giga liberi su {num_words(gb(total))}."


async def version() -> str:
    v = (await _run("/usr/bin/sw_vers", "-productVersion")).strip()
    return f"Hai macOS {v.replace('.', ' punto ')}." if v else "Non riesco a leggere la versione di macOS."             # («15.4» letto come numero sarebbe «quindici virgola quattro»)


async def uptime() -> str:
    out = await _run("/usr/sbin/sysctl", "-n", "kern.boottime")
    m = re.search(r"sec\s*=\s*(\d+)", out)
    if not m:
        return "Non riesco a leggere da quanto è acceso il Mac."
    secs = int(time.time()) - int(m.group(1))
    d, h, mi = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
    if d:
        return f"Il Mac è acceso da {'un giorno' if d == 1 else num_words(d) + ' giorni'} e {_hm(h, 0) if h else 'poche ore'}."
    return f"Il Mac è acceso da {_hm(h, mi)}."


async def wifi() -> str:
    out = await _run("/usr/sbin/networksetup", "-getairportnetwork", "en0")
    m = re.search(r"Network:\s*(.+)", out)
    if m and "<redacted>" not in m.group(1):
        return f"Sei collegato alla rete wifi {m.group(1).strip()}."
    ip = (await _run("/usr/sbin/ipconfig", "getifaddr", "en0")).strip()
    return "Sei collegato al wifi, ma macOS non mi dice come si chiama la rete." if ip else "Non risulti collegato al wifi."


async def ip() -> str:
    for ifc in ("en0", "en1"):
        v = (await _run("/usr/sbin/ipconfig", "getifaddr", ifc)).strip()
        if v:
            return "Il tuo indirizzo IP sulla rete locale è " + ", ".join(v.split(".")[:4]).replace(", ", " punto ") + "."
    return "Non risulti collegato a una rete."


async def memory() -> str:
    out = await _run("/usr/bin/memory_pressure")
    m = re.search(r"free percentage:\s*(\d+)%", out)
    total = int((await _run("/usr/sbin/sysctl", "-n", "hw.memsize")).strip() or 0)
    tot = f" su {num_words(round(total / 2**30))} giga" if total else ""
    return f"La memoria libera è circa il {_pct(int(m.group(1)))}{tot}." if m else "Non riesco a leggere la memoria."


KINDS = {"batteria": battery, "spazio": disk, "versione": version, "accensione": uptime, "wifi": wifi, "ip": ip, "memoria": memory}


async def answer(kind: str) -> str:
    fn = KINDS.get(kind.strip().lower())
    return await fn() if fn else "Questa informazione sul Mac non la so dire."
