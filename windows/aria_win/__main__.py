import sys

from . import paths


def _streams() -> None:
    """Con pythonw.exe stdout e stderr non esistono (None) e le librerie che ci scrivono sopra (barre di avanzamento, log) si rompono: si dirottano sul log."""
    if sys.stdout is None or sys.stderr is None:
        try:
            paths.logs_dir().mkdir(parents=True, exist_ok=True)
            f = open(paths.app_log(), "a", encoding="utf-8", buffering=1)
        except OSError:
            f = open("NUL", "w")
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f


_streams()

from .app import main  # noqa: E402

sys.exit(main())
