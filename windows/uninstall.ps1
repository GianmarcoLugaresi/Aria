# Toglie Aria dal PC. NON cancella i modelli di Ollama.
#   powershell -ExecutionPolicy Bypass -File .\windows\uninstall.ps1
$ErrorActionPreference = "Continue"
$Support = Join-Path $env:APPDATA "Aria"
$Local   = Join-Path $env:LOCALAPPDATA "Aria"

Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe' OR Name = 'python.exe'" |
    Where-Object { $_.ExecutablePath -like "$Local\venv\*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Remove-Item (Join-Path ([Environment]::GetFolderPath("Programs")) "Aria.lnk") -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "Aria" -ErrorAction SilentlyContinue
Remove-Item $Local -Recurse -Force -ErrorAction SilentlyContinue

$a = Read-Host "Cancello anche configurazione, carattere e memoria ($Support e $env:USERPROFILE\.aria)? [s/N]"
if ($a -match '^[sSyY]') {
    Remove-Item $Support -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $env:USERPROFILE ".aria") -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Fatto."
Write-Host "Per liberare altro spazio:  ollama rm gemma3:4b   e   cancella le cartelle models--* in $env:USERPROFILE\.cache\huggingface\hub"
