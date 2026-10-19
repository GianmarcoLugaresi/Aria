#!/usr/bin/env bash
# Compila l'app e assembla Aria.app.   Uso:  ./build_app.sh [cartella-di-destinazione]
set -euo pipefail
cd "$(dirname "$0")"
DEST="${1:-build}"
APP="$DEST/Aria.app"

swift build -c release --arch arm64
BIN="$(swift build -c release --arch arm64 --show-bin-path)/Aria"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Aria"
cp Resources/overlay.html Resources/neural.js "$APP/Contents/Resources/"
[ -f Resources/AppIcon.icns ] && cp Resources/AppIcon.icns "$APP/Contents/Resources/"
cp Resources/MenuIcon.png Resources/MenuIconMuted.png "$APP/Contents/Resources/"        # logo nella barra dei menu

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Aria</string>
  <key>CFBundleDisplayName</key><string>Aria</string>
  <key>CFBundleIdentifier</key><string>it.aria.assistente</string>
  <key>CFBundleExecutable</key><string>Aria</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.3.1</string>
  <key>CFBundleVersion</key><string>4</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppleEventsUsageDescription</key><string>Aria controlla Promemoria, Calendario, Musica e le tue Scorciatoie solo quando glielo chiedi a voce.</string>
  <key>NSMicrophoneUsageDescription</key><string>Aria ascolta la tua voce per risponderti. L'audio resta sul tuo Mac e non viene inviato a nessuno.</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
</dict></plist>
PLIST

# Firma. Con la firma «ad hoc» l'identita' dell'app e' l'impronta del file: a OGNI ricompilazione macOS la considera un'app nuova e i permessi
# (microfono, Registrazione schermo, Accessibilita') vanno ridati, anche se nelle Impostazioni Aria sembra ancora attiva.
# Se nel portachiavi c'e' un certificato per firmare codice chiamato «Aria Local» (Accesso Portachiavi > Assistente Certificati > Crea un certificato,
# tipo «Firma del codice»), si usa quello: l'identita' resta la stessa tra una versione e l'altra e i permessi restano.
IDENTITY="${ARIA_SIGN_IDENTITY:-}"
if [ -z "$IDENTITY" ]; then                                       # «Aria Local», altrimenti il certificato «Apple Development» di Xcode (gratis con l'ID Apple)
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | grep -o '"Aria Local"' | head -1 | tr -d '"' || true)"
  [ -z "$IDENTITY" ] && IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | grep -o '"Apple Development: [^"]*"' | head -1 | tr -d '"' || true)"
fi
if [ -n "$IDENTITY" ] && security find-identity -v -p codesigning 2>/dev/null | grep -q "\"$IDENTITY\""; then
  if codesign --force --deep --sign "$IDENTITY" "$APP" >/dev/null 2>&1; then
    echo "Firmata con «$IDENTITY»: i permessi restano tra una versione e l'altra."
  else                                                                # (portachiavi rifiutato o certificato scaduto: si torna alla firma ad hoc)
    codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
    echo "attenzione: firma con «$IDENTITY» non riuscita: firmata ad hoc (i permessi di macOS vanno ridati dopo l'aggiornamento)"
  fi
else
  codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "attenzione: firma non riuscita"
  echo "Firma ad hoc: dopo l'aggiornamento i permessi di macOS (microfono, schermo, Accessibilità) vanno ridati."
fi
echo "Creata: $APP"
