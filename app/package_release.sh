#!/usr/bin/env bash
# Assembla l'app scaricabile: Aria.app con dentro Python, le librerie, il programma e i programmi di supporto.
# Chi la scarica non installa niente: la apre e (al primo avvio) l'app scarica solo i modelli.
# Uso:  ./app/package_release.sh [cartella-di-uscita]        (default: app/dist)  ·  serve un Mac con chip Apple e gli strumenti di Xcode
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/app/dist}"
VERSION="${ARIA_VERSION:-$(grep -A1 CFBundleShortVersionString "$ROOT/app/build_app.sh" | grep -o '<string>[^<]*' | head -1 | sed 's/<string>//')}"
NAME="Aria-$VERSION-macos-arm64"
MINOS="${ARIA_MIN_MACOS:-26.0}"          # versione minima di macOS per cui si compilano i programmi di supporto (non quella del Mac che compila)
WORK="$(mktemp -d "${TMPDIR:-/tmp}/aria-release.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

say() { printf "\n\033[1m== %s\033[0m\n" "$1"; }

[ "$(uname -m)" = "arm64" ] || { echo "Serve un Mac con chip Apple (arm64)."; exit 1; }
command -v swift >/dev/null 2>&1 || { echo "Mancano gli strumenti di Xcode:  xcode-select --install"; exit 1; }
command -v uv >/dev/null 2>&1 || { echo "Manca 'uv' (https://docs.astral.sh/uv/)."; exit 1; }
[ -n "$VERSION" ] || { echo "Versione non trovata in app/build_app.sh"; exit 1; }

say "1/7 L'app (Swift)"
ARIA_SIGN_IDENTITY="-" "$ROOT/app/build_app.sh" "$WORK" >/dev/null
APP="$WORK/Aria.app"
RES="$APP/Contents/Resources"
BACKEND="$RES/backend"
[ -d "$APP" ] || { echo "Compilazione dell'app non riuscita."; exit 1; }

say "2/7 Python portatile"
uv python install cpython-3.12-macos-aarch64 -q
PYBIN="$(uv python find --managed-python cpython-3.12-macos-aarch64)"
PYROOT="$(cd "$(dirname "$(python3 -c 'import os,sys;print(os.path.realpath(sys.argv[1]))' "$PYBIN")")/.." && pwd)"
echo "da: $PYROOT"
ditto "$PYROOT" "$BACKEND"
rm -f "$BACKEND/lib/python3.12/EXTERNALLY-MANAGED"
PY="$BACKEND/bin/python3.12"

say "3/7 Librerie (versioni fissate in app/release-requirements.txt)"
uv pip install --python "$PY" -q --no-deps -r "$ROOT/app/release-requirements.txt"

say "4/7 Il programma di Aria e i programmi di supporto"
mkdir -p "$BACKEND/software" "$RES/bin" "$RES/defaults"
rsync -a --exclude "__pycache__" "$ROOT/software/aria/" "$BACKEND/software/aria/"
for pair in "aria_apple_stt:aria-apple-stt:-parse-as-library" "aria_vpmic:aria-vpmic:" "aria_apple_ocr:aria-apple-ocr:" "aria_ax:aria-ax:" "aria_pointer:aria-pointer:"; do
  src="${pair%%:*}"; rest="${pair#*:}"; bin="${rest%%:*}"; flag="${rest#*:}"
  # shellcheck disable=SC2086
  swiftc $flag -O -target "arm64-apple-macos$MINOS" "$ROOT/software/helpers/$src.swift" -o "$RES/bin/$bin" 2>/dev/null || { echo "Compilazione di $bin non riuscita."; exit 1; }
done
cp "$ROOT/app/config.app.yaml" "$RES/defaults/config.yaml"
cp "$ROOT/anima/persona_compatta.md" "$RES/defaults/persona.md"

say "5/7 Alleggerimento"
rm -rf "$BACKEND/include" "$BACKEND/share" "$BACKEND/lib/python3.12/test" "$BACKEND/lib/python3.12/idlelib" "$BACKEND/lib/python3.12/turtledemo" \
       "$BACKEND/lib/python3.12/config-3.12-darwin"
rm -f "$BACKEND/bin/"{idle3,idle3.12,2to3,2to3-3.12,pydoc3,pydoc3.12,python3-config,python3.12-config}
SP="$BACKEND/lib/python3.12/site-packages"
rm -rf "$SP/torch/include" "$SP/torch/share" "$SP/torch/test" "$SP/mlx/include" "$SP/mlx/share" "$SP/numpy/_core/include" "$SP/pip"
# via dal pacchetto i percorsi del Mac che lo costruisce (cartella personale, cartelle di lavoro)
sed -i '' "s#$PYROOT#/opt/aria-python#g" "$BACKEND/lib/python3.12/_sysconfigdata__darwin_darwin.py"
install_name_tool -id "@executable_path/../lib/libpython3.12.dylib" "$BACKEND/lib/libpython3.12.dylib"
strip -x -S "$APP/Contents/MacOS/Aria"
find "$BACKEND" -name "__pycache__" -type d -prune -exec rm -rf {} +
# bytecode gia' pronto, senza controllo sulla data dei file (l'app e' firmata e sigillata: dopo non si scrive piu' dentro)
"$PY" -m compileall -q -j 0 -f --invalidation-mode unchecked-hash "$BACKEND/lib" "$BACKEND/software" >/dev/null 2>&1 || true
du -sh "$BACKEND" | sed 's/^/backend: /'

plutil -replace LSMinimumSystemVersion -string "$MINOS" "$APP/Contents/Info.plist"       # sotto macOS 26 l'app si rifiuta di aprirsi con un messaggio chiaro invece di rompersi

say "6/7 Firma (ad hoc)"
"$PY" -I - "$APP" <<'PY' > "$WORK/macho.lst"
import os, sys
magic = {b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa\xcf", b"\xbe\xba\xfe\xca"}
for dp, _, fs in os.walk(sys.argv[1]):
    for f in fs:
        p = os.path.join(dp, f)
        if os.path.islink(p) or not os.path.isfile(p) or p.endswith("/Contents/MacOS/" + f):
            continue                                                  # (il programma principale lo firma l'app intera, qui sotto)
        try:
            with open(p, "rb") as h:
                if h.read(4) in magic:
                    sys.stdout.write(p + "\0")
        except OSError:
            pass
PY
tr -cd '\0' < "$WORK/macho.lst" | wc -c | sed 's/^ *//; s/$/ file eseguibili da firmare/'
xargs -0 -n 25 -P 8 codesign --force --sign - --timestamp=none < "$WORK/macho.lst" 2>&1 | grep -v "replacing existing signature" || true
codesign --force --sign - --timestamp=none "$APP"
codesign --verify --deep --strict "$APP" && echo "firma verificata"

if LC_ALL=C grep -rlaF -e "/Users/$(id -un)" -e "claude-" "$APP" 2>/dev/null | head -5 | grep .; then
  echo "attenzione: nel pacchetto restano percorsi del Mac che lo ha costruito (vedi sopra)"
fi

say "7/7 Archivio"
mkdir -p "$OUT"
rm -f "$OUT/$NAME.zip" "$OUT/$NAME.zip.sha256"
ditto -c -k --keepParent "$APP" "$OUT/$NAME.zip"
(cd "$OUT" && shasum -a 256 "$NAME.zip" > "$NAME.zip.sha256")
ls -lh "$OUT/$NAME.zip"
cat "$OUT/$NAME.zip.sha256"
