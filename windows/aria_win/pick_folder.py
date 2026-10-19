"""Finestra «scegli la cartella di Aria» (tkinter), in un processo a parte: stampa il percorso scelto, niente se annulla."""
import sys


def main() -> int:
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    folder = filedialog.askdirectory(title="Scegli la cartella dove Aria legge e scrive i file", mustexist=True)
    root.destroy()
    if folder:
        print(folder)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
