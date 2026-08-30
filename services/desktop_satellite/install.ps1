# Instalacja zbudowanej satelity na tym komputerze (Windows).
#
#     .\install.ps1              # instaluje i uruchamia
#     .\install.ps1 -NoStart     # tylko kopiuje pliki
#
# Kopiuje dist\regis-satellite\ do %LOCALAPPDATA%\Programs\Regis, tworzy skrót
# w menu Start i — jeśli istnieje lokalna konfiguracja ze źródeł — proponuje
# przeniesienie sender_id, żeby nie trzeba było rejestrować satelity od nowa.
#
# Autostartu NIE włącza: to przełącznik w menu zasobnika, świadoma decyzja
# użytkownika (patrz autostart.py).

param([switch]$NoStart)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$source = Join-Path $PSScriptRoot "dist\regis-satellite"
if (-not (Test-Path $source)) { throw "Brak $source — uruchom najpierw .\build.ps1" }

$target = Join-Path $env:LOCALAPPDATA "Programs\Regis"
$appData = Join-Path $env:APPDATA "Regis"

Write-Host "==> Zatrzymywanie działającej instancji" -ForegroundColor Cyan
Get-Process regis-satellite -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "==> Kopiowanie do $target" -ForegroundColor Cyan
if (Test-Path $target) { Remove-Item -Recurse -Force $target }
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Recurse -Force "$source\*" $target

# Wersja zainstalowana trzyma konfigurację w %APPDATA%\Regis, a uruchomienie ze
# źródeł w services/desktop_satellite/config. To dwie różne lokalizacje, więc bez
# przeniesienia sender_id nowa instalacja dostałaby nowy UUID i wypadła z rejestru
# klientów w Web UI (patrz config.py).
$legacyConfig = Join-Path $PSScriptRoot "config\settings.json"
$newConfig = Join-Path $appData "settings.json"
if ((Test-Path $legacyConfig) -and -not (Test-Path $newConfig)) {
    Write-Host "==> Przenoszenie dotychczasowego sender_id" -ForegroundColor Cyan
    New-Item -ItemType Directory -Force -Path $appData | Out-Null
    Copy-Item $legacyConfig $newConfig
    Write-Host "    $((Get-Content $newConfig | ConvertFrom-Json).sender_id)"
}

Write-Host "==> Skrót w menu Start" -ForegroundColor Cyan
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Regis Satellite.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($startMenu)
$shortcut.TargetPath = Join-Path $target "regis-satellite.exe"
$shortcut.Arguments = ""
$shortcut.WorkingDirectory = $target
$shortcut.Description = "Satelita głosowa Regis"
$shortcut.Save()

Write-Host ""
Write-Host "Zainstalowano w $target" -ForegroundColor Green
Write-Host "Konfiguracja: $appData"
Write-Host "Logi:         $appData\logs\satellite.log"
Write-Host ""
Write-Host "Dalsze kroki:"
Write-Host "  1. Uruchom aplikację (skrót w menu Start) — ikona pojawi się w zasobniku."
Write-Host "  2. Z menu ikony skopiuj sender_id."
Write-Host "  3. W Web UI serwera: Ustawienia -> Klienci -> zatwierdź nowego nadawcę i przypisz pokój."
Write-Host "  4. W menu ikony włącz 'Uruchamiaj przy starcie systemu', jeśli tego chcesz."

if (-not $NoStart) {
    Write-Host ""
    Write-Host "==> Uruchamianie" -ForegroundColor Cyan
    Start-Process (Join-Path $target "regis-satellite.exe")
}
