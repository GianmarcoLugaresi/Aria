# Installa Aria per Windows: ambiente Python, programma, configurazione, icona nella barra delle applicazioni.
# Installs Aria for Windows: Python environment, program, configuration, tray icon.
#
#   powershell -ExecutionPolicy Bypass -File .\windows\install.ps1            (dalla cartella del progetto / from the project folder)
#   ... -Gpu                  Whisper sulla scheda NVIDIA (CUDA 12): molto più veloce e preciso del processore / Whisper on an NVIDIA card (CUDA 12)
#   ... -Modello qwen3:4b     un altro chatbot di Ollama (predefinito: gemma3:4b, circa 3,3 GB) / another Ollama chatbot (alias -Model)
#   ... -Si                   non fa domande (installa Ollama e scarica il chatbot da solo) / asks nothing (alias -Yes)
#   ... -Lingua en            la lingua di Aria e di questo script: it, en o auto (come Windows) / Aria's language and this script's (alias -Language)
#
# Si può rilanciare per aggiornare: non tocca la tua configurazione. / Safe to re-run to update: it keeps your configuration.
param(
    [switch]$Gpu,
    [Alias("Model")][string]$Modello = "gemma3:4b",
    [Alias("Language")][ValidateSet("auto", "it", "en")][string]$Lingua = "auto",
    [Alias("Yes")][switch]$Si
)
$ErrorActionPreference = "Stop"

$Root     = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Support  = Join-Path $env:APPDATA "Aria"
$Local    = Join-Path $env:LOCALAPPDATA "Aria"
$Venv     = Join-Path $Local "venv"
$Py       = Join-Path $Venv "Scripts\python.exe"
$Pyw      = Join-Path $Venv "Scripts\pythonw.exe"
$Software = Join-Path $Local "software"
$Res      = Join-Path $Local "resources"

# La lingua dei messaggi: -Lingua, altrimenti la lingua di Windows (italiano solo se Windows e' in italiano). / Message language: -Lingua, else Windows' display language.
$IsIt = if ($Lingua -eq "it") { $true } elseif ($Lingua -eq "en") { $false } else { (Get-UICulture).TwoLetterISOLanguageName -eq "it" }
function T($ita, $eng) { if ($script:IsIt) { $ita } else { $eng } }       # (in PowerShell i nomi delle variabili non distinguono maiuscole e minuscole: niente $IT con un parametro $it)

function Say($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Ask($question) {
    if ($Si) { return $true }
    $a = Read-Host ($question + " [" + (T "s/N" "y/N") + "]")
    return ($a -match '^[sSyY]')
}
function Check($what) {
    if ($LASTEXITCODE -ne 0) { throw ($what + (T " non è riuscito (codice " " failed (code ") + $LASTEXITCODE + ")") }
}
function Copy-Tree($from, $to) {
    robocopy $from $to /MIR /XD __pycache__ .pytest_cache /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw (T "copia di $from non riuscita (robocopy $LASTEXITCODE)" "copying $from failed (robocopy $LASTEXITCODE)") }
    $global:LASTEXITCODE = 0
}

Say (T "Controlli" "Checks")
if (-not [Environment]::Is64BitOperatingSystem) { throw (T "Serve Windows a 64 bit." "64-bit Windows is required.") }
if ([Environment]::OSVersion.Version.Build -lt 17763) { throw (T "Serve Windows 10 (versione 1809) o Windows 11." "Windows 10 (version 1809) or Windows 11 is required.") }
$webview2 = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
if (-not $webview2) { $webview2 = Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue }
if (-not $webview2) {
    Write-Host (T "Manca il componente «WebView2 Runtime» di Microsoft (c'è già in Windows 11): senza, Aria funziona ma non mostra la schermata con l'onda." "Microsoft's WebView2 Runtime is missing (Windows 11 already has it): without it Aria works but does not show the wave overlay.") -ForegroundColor Yellow
    Write-Host (T "Scaricalo da https://developer.microsoft.com/microsoft-edge/webview2/ e rilancia questo script." "Download it from https://developer.microsoft.com/microsoft-edge/webview2/ and run this script again.")
}

Say (T "1/6 Python (uv)" "1/6 Python (uv)")
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host (T "Installo 'uv' (gestore Python di Astral, dal sito ufficiale)…" "Installing 'uv' (Astral's Python manager, from the official site)...")
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
New-Item -ItemType Directory -Force -Path $Local, $Support | Out-Null
if (-not (Test-Path $Py)) { uv venv $Venv --python 3.12; Check (T "Creazione dell'ambiente Python" "Creating the Python environment") }

Say (T "2/6 Librerie (Whisper, voce Pocket TTS, rilevamento voce, ricerca web)" "2/6 Libraries (Whisper, Pocket TTS voice, voice detection, web search)")
uv pip install --python $Py -r (Join-Path $Root "windows\requirements-backend.txt")
Check (T "Installazione delle librerie" "Installing the libraries")
if ($Gpu) {
    Write-Host (T "Librerie CUDA per Whisper su NVIDIA (circa 1 GB)…" "CUDA libraries for Whisper on NVIDIA (about 1 GB)...")
    uv pip install --python $Py "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
    Check (T "Installazione delle librerie CUDA" "Installing the CUDA libraries")
}
Say (T "3/6 Il programma di Aria e l'icona nella barra" "3/6 Aria's program and the tray icon")
Copy-Tree (Join-Path $Root "software\aria") (Join-Path $Software "aria")
uv pip install --python $Py --reinstall (Join-Path $Root "windows")
Check (T "Installazione dell'icona e della schermata" "Installing the icon and the overlay")
uv pip install --python $Py pycaw
if ($LASTEXITCODE -ne 0) { Write-Host (T "(pycaw non installato: il volume a voce userà i tasti del volume)" "(pycaw not installed: the volume by voice will use the volume keys)") }
New-Item -ItemType Directory -Force -Path $Res | Out-Null
foreach ($f in "overlay.html", "neural.js", "MenuIcon.png", "MenuIconMuted.png") { Copy-Item (Join-Path $Root "app\Resources\$f") $Res -Force }
Copy-Item (Join-Path $Root "windows\assets\aria.ico") $Res -Force

if (-not (Test-Path (Join-Path $Support "config.yaml"))) {
    $cfg = Get-Content (Join-Path $Root "windows\config.windows.yaml") -Raw -Encoding UTF8
    if ($Gpu) {
        $cfg = $cfg -replace "stt: \{kind: faster-whisper, model: small, compute_type: int8\}", "stt: {kind: faster-whisper, model: large-v3-turbo, device: cuda, compute_type: float16}"
    }
    [IO.File]::WriteAllText((Join-Path $Support "config.yaml"), ($cfg -replace 'model: "gemma3:4b"', "model: `"$Modello`""), (New-Object Text.UTF8Encoding $false))
}
if (-not (Test-Path (Join-Path $Support "persona.md"))) {
    Copy-Item (Join-Path $Root "anima\persona_compatta.md") (Join-Path $Support "persona.md")
}
$paths = @{ python = $Py; software = $Software; config = (Join-Path $Support "config.yaml") } | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $Support "paths.json"), $paths, (New-Object Text.UTF8Encoding $false))
if ($Lingua -ne "auto") {                                   # la lingua di Aria (stessa scelta del menu dell'icona): it o en; con "auto" segue Windows
    $env:PYTHONPATH = $Software
    $env:PYTHONUTF8 = "1"
    & $Py -m aria.models language set $Lingua --config (Join-Path $Support "config.yaml") | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Host (T "Non sono riuscita a impostare la lingua: la scegli dal menu dell'icona (Lingua)." "I could not set the language: pick it from the tray icon menu (Language).") -ForegroundColor Yellow; $global:LASTEXITCODE = 0 }
}

Say (T "4/6 Chatbot (Ollama)" "4/6 Chatbot (Ollama)")
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue)
if (-not $ollama) { $cand = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"; if (Test-Path $cand) { $ollama = $cand } }
if (-not $ollama) {
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Ask (T "Ollama non c'è. Lo installo con winget?" "Ollama is not installed. Install it with winget?"))) {
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
        $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    } else {
        Write-Host (T "Installa Ollama da https://ollama.com, poi esegui:  ollama pull $Modello" "Install Ollama from https://ollama.com, then run:  ollama pull $Modello") -ForegroundColor Yellow
    }
}
$ollamaPath = if ($ollama -is [Management.Automation.ApplicationInfo]) { $ollama.Source } elseif ($ollama) { [string]$ollama } else { $null }
if ($ollamaPath -and (Test-Path $ollamaPath)) {
    $have = (& $ollamaPath list 2>$null) -join "`n"
    if ($have -match [regex]::Escape($Modello)) { Write-Host (T "già presente ($Modello)" "already there ($Modello)") }
    elseif (Ask (T "Scarico $Modello con Ollama (circa 3,3 GB)?" "Download $Modello with Ollama (about 3.3 GB)?")) {
        & $ollamaPath pull $Modello
        Check (T "Download del chatbot" "Downloading the chatbot")
    }
    else { Write-Host (T "Salto: ricordati di eseguire  ollama pull $Modello" "Skipped: remember to run  ollama pull $Modello") }
} elseif ($ollama) {
    Write-Host (T "Ollama è installato ma non lo trovo ancora: apri un nuovo PowerShell ed esegui  ollama pull $Modello" "Ollama is installed but I cannot find it yet: open a new PowerShell and run  ollama pull $Modello") -ForegroundColor Yellow
}

Say (T "5/6 Modelli di voce e riconoscimento (solo la prima volta)" "5/6 Voice and recognition models (first time only)")
$env:PYTHONPATH = $Software
$env:PYTHONUTF8 = "1"
try { & $Py -m aria.main --prefetch --config (Join-Path $Support "config.yaml") } catch { Write-Host (T "Prefetch non completato: i modelli si scaricheranno al primo avvio." "Prefetch did not finish: the models will download on first launch.") -ForegroundColor Yellow }

Say (T "6/6 Collegamento nel menu Start" "6/6 Start menu shortcut")
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Aria.lnk"
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $Pyw
$s.Arguments = "-m aria_win"
$s.WorkingDirectory = $Local
$s.IconLocation = (Join-Path $Res "aria.ico")
$s.Description = (T "Aria, l'assistente vocale" "Aria, the voice assistant")
$s.Save()

if ($IsIt) {
Write-Host @"

Fatto.  Apri Aria dal menu Start (cerca «Aria») oppure:   & '$Pyw' -m aria_win
  • compare l'icona nella barra delle applicazioni (accanto all'orologio, forse sotto la freccia ^)
  • di' «Hey Aria» oppure premi  Ctrl + Alt + Spazio
  • dal menu dell'icona: voce, lingua, silenzio, «Avvia con Windows», cartella di Aria, configurazione
Configurazione: $Support\config.yaml   ·   Carattere: $Support\persona.md   ·   Log: $Local\Logs
"@
} else {
Write-Host @"

Done.  Open Aria from the Start menu (search for "Aria") or:   & '$Pyw' -m aria_win
  - the icon appears in the taskbar tray (next to the clock, maybe under the ^ arrow)
  - say "Hey Aria" or press  Ctrl + Alt + Space
  - from the icon menu: voice, language, mute, "Start with Windows", Aria's folder, configuration
Configuration: $Support\config.yaml   -   Personality: $Support\persona.md (persona.en.md in English)   -   Logs: $Local\Logs
"@
}
if (Ask (T "Apro Aria adesso?" "Open Aria now?")) { Start-Process $Pyw -ArgumentList "-m", "aria_win" -WorkingDirectory $Local }
