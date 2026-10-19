# Installa Aria per Windows: ambiente Python, programma, configurazione, icona nella barra delle applicazioni.
#
#   powershell -ExecutionPolicy Bypass -File .\windows\install.ps1            (dalla cartella del progetto)
#   ... -Gpu                  Whisper sulla scheda NVIDIA (CUDA 12): molto più veloce e preciso del processore
#   ... -Modello qwen3:4b     un altro chatbot di Ollama (predefinito: gemma3:4b, circa 3,3 GB)
#   ... -Si                   non fa domande (installa Ollama e scarica il chatbot da solo)
#
# Si può rilanciare per aggiornare: non tocca la tua configurazione.
param(
    [switch]$Gpu,
    [string]$Modello = "gemma3:4b",
    [switch]$Si
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

function Say($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Ask($question) {
    if ($Si) { return $true }
    $a = Read-Host "$question [s/N]"
    return ($a -match '^[sSyY]')
}
function Check($what) {
    if ($LASTEXITCODE -ne 0) { throw "$what non è riuscito (codice $LASTEXITCODE)" }
}
function Copy-Tree($from, $to) {
    robocopy $from $to /MIR /XD __pycache__ .pytest_cache /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copia di $from non riuscita (robocopy $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
}

Say "Controlli"
if (-not [Environment]::Is64BitOperatingSystem) { throw "Serve Windows a 64 bit." }
if ([Environment]::OSVersion.Version.Build -lt 17763) { throw "Serve Windows 10 (versione 1809) o Windows 11." }
$webview2 = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
if (-not $webview2) { $webview2 = Get-ItemProperty "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue }
if (-not $webview2) {
    Write-Host "Manca il componente «WebView2 Runtime» di Microsoft (c'è già in Windows 11): senza, Aria funziona ma non mostra la schermata con l'onda." -ForegroundColor Yellow
    Write-Host "Scaricalo da https://developer.microsoft.com/microsoft-edge/webview2/ e rilancia questo script."
}

Say "1/6 Python (uv)"
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installo 'uv' (gestore Python di Astral, dal sito ufficiale)…"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
New-Item -ItemType Directory -Force -Path $Local, $Support | Out-Null
if (-not (Test-Path $Py)) { uv venv $Venv --python 3.12; Check "Creazione dell'ambiente Python" }

Say "2/6 Librerie (Whisper, voce Pocket TTS, rilevamento voce, ricerca web)"
uv pip install --python $Py -r (Join-Path $Root "windows\requirements-backend.txt")
Check "Installazione delle librerie"
if ($Gpu) {
    Write-Host "Librerie CUDA per Whisper su NVIDIA (circa 1 GB)…"
    uv pip install --python $Py "nvidia-cublas-cu12" "nvidia-cudnn-cu12==9.*"
    Check "Installazione delle librerie CUDA"
}
Say "3/6 Il programma di Aria e l'icona nella barra"
Copy-Tree (Join-Path $Root "software\aria") (Join-Path $Software "aria")
uv pip install --python $Py --reinstall (Join-Path $Root "windows")
Check "Installazione dell'icona e della schermata"
uv pip install --python $Py pycaw
if ($LASTEXITCODE -ne 0) { Write-Host "(pycaw non installato: il volume a voce userà i tasti del volume)" }
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

Say "4/6 Chatbot (Ollama)"
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue)
if (-not $ollama) { $cand = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"; if (Test-Path $cand) { $ollama = $cand } }
if (-not $ollama) {
    if ((Get-Command winget -ErrorAction SilentlyContinue) -and (Ask "Ollama non c'è. Lo installo con winget?")) {
        winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
        $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    } else {
        Write-Host "Installa Ollama da https://ollama.com, poi esegui:  ollama pull $Modello" -ForegroundColor Yellow
    }
}
$ollamaPath = if ($ollama -is [Management.Automation.ApplicationInfo]) { $ollama.Source } elseif ($ollama) { [string]$ollama } else { $null }
if ($ollamaPath -and (Test-Path $ollamaPath)) {
    $have = (& $ollamaPath list 2>$null) -join "`n"
    if ($have -match [regex]::Escape($Modello)) { Write-Host "già presente ($Modello)" }
    elseif (Ask "Scarico $Modello con Ollama (circa 3,3 GB)?") {
        & $ollamaPath pull $Modello
        Check "Download del chatbot"
    }
    else { Write-Host "Salto: ricordati di eseguire  ollama pull $Modello" }
} elseif ($ollama) {
    Write-Host "Ollama è installato ma non lo trovo ancora: apri un nuovo PowerShell ed esegui  ollama pull $Modello" -ForegroundColor Yellow
}

Say "5/6 Modelli di voce e riconoscimento (solo la prima volta)"
$env:PYTHONPATH = $Software
$env:PYTHONUTF8 = "1"
try { & $Py -m aria.main --prefetch --config (Join-Path $Support "config.yaml") } catch { Write-Host "Prefetch non completato: i modelli si scaricheranno al primo avvio." -ForegroundColor Yellow }

Say "6/6 Collegamento nel menu Start"
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Aria.lnk"
$sh = New-Object -ComObject WScript.Shell
$s = $sh.CreateShortcut($lnk)
$s.TargetPath = $Pyw
$s.Arguments = "-m aria_win"
$s.WorkingDirectory = $Local
$s.IconLocation = (Join-Path $Res "aria.ico")
$s.Description = "Aria, l'assistente vocale"
$s.Save()

Write-Host @"

Fatto.  Apri Aria dal menu Start (cerca «Aria») oppure:   & '$Pyw' -m aria_win
  • compare l'icona nella barra delle applicazioni (accanto all'orologio, forse sotto la freccia ^)
  • di' «Hey Aria» oppure premi  Ctrl + Alt + Spazio
  • dal menu dell'icona: voce, silenzio, «Avvia con Windows», cartella di Aria, configurazione
Configurazione: $Support\config.yaml   ·   Carattere: $Support\persona.md   ·   Log: $Local\Logs
"@
if (Ask "Apro Aria adesso?") { Start-Process $Pyw -ArgumentList "-m", "aria_win" -WorkingDirectory $Local }
