# Toglie Aria dal PC. NON cancella i modelli di Ollama. / Removes Aria from the PC. It does NOT delete Ollama's models.
#   powershell -ExecutionPolicy Bypass -File .\windows\uninstall.ps1            (-Lingua it|en per scegliere la lingua dei messaggi / to pick the message language)
param(
    [Alias("Language")][ValidateSet("auto", "it", "en")][string]$Lingua = "auto"
)
$ErrorActionPreference = "Continue"
$Support = Join-Path $env:APPDATA "Aria"
$Local   = Join-Path $env:LOCALAPPDATA "Aria"

# La lingua dei messaggi: -Lingua, altrimenti quella scelta nel menu di Aria (settings.json), altrimenti la lingua di Windows. / -Lingua, else Aria's menu choice, else Windows' language.
$IsIt = (Get-UICulture).TwoLetterISOLanguageName -eq "it"
$chosen = $Lingua
if ($chosen -eq "auto") {
    try { $chosen = (Get-Content (Join-Path $Support "settings.json") -Raw -Encoding UTF8 | ConvertFrom-Json).language } catch { $chosen = "auto" }
}
if ($chosen -match '^it') { $IsIt = $true } elseif ($chosen -match '^en') { $IsIt = $false }
function T($ita, $eng) { if ($script:IsIt) { $ita } else { $eng } }       # (in PowerShell i nomi delle variabili non distinguono maiuscole e minuscole)

Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.ExecutablePath -like "$Local\venv\*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Remove-Item (Join-Path ([Environment]::GetFolderPath("Programs")) "Aria.lnk") -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Aria" -ErrorAction SilentlyContinue
Remove-Item $Local -Recurse -Force -ErrorAction SilentlyContinue

$a = Read-Host (T "Cancello anche configurazione, carattere e memoria ($Support e $env:USERPROFILE\.aria)? [s/N]" "Also delete configuration, personality and memory ($Support and $env:USERPROFILE\.aria)? [y/N]")
if ($a -match '^[sSyY]') {
    Remove-Item $Support -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $env:USERPROFILE ".aria") -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host (T "Fatto." "Done.")
Write-Host (T "Per liberare altro spazio:  ollama rm gemma3:4b   e   cancella le cartelle models--* in $env:USERPROFILE\.cache\huggingface\hub" "To free more space:  ollama rm gemma3:4b   and delete the models--* folders in $env:USERPROFILE\.cache\huggingface\hub")
