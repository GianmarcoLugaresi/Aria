"""L'icona nella barra delle applicazioni (accanto all'orologio) e il suo menu: l'equivalente della barra dei menu del Mac."""
from __future__ import annotations

from . import paths, win32
from .l10n import tr
from .model import AppModel

ICON_SIZE = 64


def make_icon_image(model: AppModel):
    """Il logo di Aria (la stessa immagine dell'app per Mac): bianco su tema scuro, nero su tema chiaro, a colori quando lavora."""
    from PIL import Image
    src = paths.resources_dir() / ("MenuIconMuted.png" if model.muted else "MenuIcon.png")
    try:
        mask = Image.open(src).convert("RGBA").resize((ICON_SIZE, ICON_SIZE), Image.LANCZOS)
    except OSError:
        return Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (176, 190, 255, 255))
    color = model.icon_color()
    if color is None:
        color = (0, 0, 0) if win32.system_uses_light_theme() else (255, 255, 255)
    img = Image.new("RGBA", mask.size, color + (0,))
    img.putalpha(mask.getchannel("A"))
    return img


class Tray:
    def __init__(self, model: AppModel, actions: dict):
        """actions: wake, stop, set_voice(name), set_language(code), toggle_mute, toggle_autostart, pick_folder, open_config, open_persona, open_logs, quit."""
        self.model, self.actions = model, actions
        self.icon = None

    def _menu(self):
        from pystray import Menu, MenuItem as Item
        a, m = self.actions, self.model

        def voice_items():                                          # (un menu che si ricostruisce da solo: cambiando lingua cambiano le voci e i titoli)
            out = []
            for title, names in m.voice_groups():
                out.append(Item(title, None, enabled=False))
                out.extend(Item(n.capitalize(), (lambda *_, n=n: a["set_voice"](n)), checked=(lambda _it, n=n: m.voice == n), radio=True) for n in names)
                out.append(Menu.SEPARATOR)
            return tuple(out)

        def language_item(code: str, text):
            return Item(text, (lambda *_, code=code: a["set_language"](code)), checked=(lambda _it, code=code: m.language_choice == code), radio=True)
        return Menu(
            Item(lambda _it: f"{m.wake_label()}   ({m.hotkey_text()})", lambda *_: a["stop"]() if m.state != "idle" else a["wake"](), default=True),
            Menu.SEPARATOR,
            Item(lambda _it: m.status_text(), None, enabled=False),
            Menu.SEPARATOR,
            Item(lambda _it: m.labels()["voice"], Menu(voice_items)),
            Item(lambda _it: m.labels()["language"], Menu(
                language_item("auto", lambda _it: m.labels()["lang_auto"]),
                language_item("it", "Italiano"),
                language_item("en", "English"))),
            Item(lambda _it: m.labels()["mute"], lambda *_: a["toggle_mute"](), checked=lambda _it: m.muted),
            Item(lambda _it: m.labels()["autostart"], lambda *_: a["toggle_autostart"](), checked=lambda _it: m.autostart),
            Menu.SEPARATOR,
            Item(lambda _it: m.labels()["folder"], lambda *_: a["pick_folder"]()),
            Item(lambda _it: m.labels()["config"], lambda *_: a["open_config"]()),
            Item(lambda _it: m.labels()["persona"], lambda *_: a["open_persona"]()),
            Item(lambda _it: m.labels()["logs"], lambda *_: a["open_logs"]()),
            Menu.SEPARATOR,
            Item(lambda _it: m.labels()["quit"], lambda *_: a["quit"]()),
        )

    def start(self) -> None:
        import pystray
        self.icon = pystray.Icon("Aria", make_icon_image(self.model), "Aria", self._menu())
        self.icon.run_detached()

    def refresh(self) -> None:
        """Dopo un cambio di stato: nuova icona (colore) e menu aggiornato (testi e spunte)."""
        if self.icon is None:
            return
        try:
            self.icon.icon = make_icon_image(self.model)
            self.icon.update_menu()
        except Exception as e:                                                          # noqa: BLE001
            paths.log(tr(f"icona: non riesco ad aggiornarla ({e})", f"icon: I can't update it ({e})"))

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:                                                           # noqa: BLE001
                pass
