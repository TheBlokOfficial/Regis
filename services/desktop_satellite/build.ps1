# Budowa satelity desktopowej dla Windows.
#
#     .\build.ps1
#
# Wynik: dist\regis-satellite\ - katalog gotowy do skopiowania na maszyne docelowa
# albo do zainstalowania lokalnie przez .\install.ps1.

# Bez `$ErrorActionPreference = "Stop"`: w Windows PowerShell 5.1 to ustawienie zamienia
# KAZDA linie na stderr z natywnego programu w blad krytyczny, a `uv` pisze tam rzeczy
# calkiem normalne (np. "Python 3.13.15 is already installed"). Bledy wykrywamy przez
# jawne $LASTEXITCODE, ktore dla natywnych plikow wykonywalnych jest jedynym wiarygodnym
# zrodlem prawdy.
Set-Location $PSScriptRoot

function Assert-Ok([string]$What) {
    if ($LASTEXITCODE -ne 0) { throw "$What zakonczylo sie kodem $LASTEXITCODE." }
}

# DOKLADNA wersja, nie "3.13": `uv python find` dopasowuje pierwszy pasujacy interpreter,
# a to bywa Python systemowy albo conda. Pelny numer jest jedynym sposobem, zeby trafic
# w interpreter zarzadzany przez uv.
$PythonVersion = "3.13.15"

Write-Host "==> Interpreter zarzadzany przez uv ($PythonVersion)" -ForegroundColor Cyan
# Budujemy samodzielnym interpreterem uv, nie tym, co deweloper ma w PATH. Powod jest
# praktyczny, nie estetyczny: build zrobiony przez `uv run` na wspoldzielonym `.venv`
# tego monorepo dal aplikacje, ktora padala przy starcie na
# "DLL load failed while importing _ssl" - do bundla trafil niespojny komplet DLL-i
# OpenSSL. Interpreter uv jest kompletny, taki sam na kazdej maszynie i niezalezny od
# tego, co deweloper ma zainstalowane obok.
python -m uv python install $PythonVersion
Assert-Ok "uv python install"

# Wyjscie zbierane w CALOSCI przed filtrowaniem: `| Select-Object -First 1` zamyka
# potok wczesniej i PowerShell ubija natywny proces, przez co $LASTEXITCODE robi sie -1
# mimo poprawnego wykonania.
$found = python -m uv python find --managed-python $PythonVersion
Assert-Ok "uv python find"
$Interpreter = ("$($found | Select-Object -First 1)").Trim()
if (-not $Interpreter) { throw "Nie znaleziono interpretera zarzadzanego $PythonVersion." }
Write-Host "    $Interpreter"

Write-Host "==> Zaleznosci buildu (osobne srodowisko .venv-build)" -ForegroundColor Cyan
# WLASNE srodowisko, nie glowne `.venv`: to monorepo `uv workspace`, wiec
# `uv sync --package desktop_satellite` przestawiloby wspolne `.venv` na same zaleznosci
# satelity i zostawilo srodowisko serwera niesprawne az do kolejnego `uv sync`.
# Build nie ma prawa psuc srodowiska deweloperskiego.
$env:UV_PROJECT_ENVIRONMENT = Join-Path $PSScriptRoot ".venv-build"
if (Test-Path .venv-build) { Remove-Item -Recurse -Force .venv-build }
python -m uv sync --package desktop_satellite --group build --python $Interpreter
Assert-Ok "uv sync"

Write-Host "==> Czyszczenie poprzedniego buildu" -ForegroundColor Cyan
if (Test-Path dist)  { Remove-Item -Recurse -Force dist }
if (Test-Path build) { Remove-Item -Recurse -Force build }

Write-Host "==> PyInstaller (--onedir, --noconsole)" -ForegroundColor Cyan
# Wprost z .venv-build, nie przez `uv run` - patrz komentarz o interpreterze wyzej.
& (Join-Path $PSScriptRoot ".venv-build\Scripts\pyinstaller.exe") regis-satellite.spec --noconfirm
Assert-Ok "PyInstaller"

Write-Host "==> Weryfikacja bundla" -ForegroundColor Cyan
# Brak tych bibliotek nie wywala BUILDA, tylko GOTOWA aplikacje, i to nie od razu:
# PortAudio dopiero przy probie otwarcia mikrofonu, czyli po pierwszym wake-wordzie.
# Sprawdzamy tutaj, zeby nie dowiedziec sie o tym na maszynie docelowej.
$internal = Join-Path $PSScriptRoot "dist\regis-satellite\_internal"
$checks = @(
    @{ Name = "PortAudio (mikrofon)";     Path = "_sounddevice_data\portaudio-binaries\libportaudio64bit.dll" },
    @{ Name = "OpenSSL (polaczenie WS)";  Path = "libssl-3-x64.dll" }
)
foreach ($check in $checks) {
    if (Test-Path (Join-Path $internal $check.Path)) {
        Write-Host "    OK  $($check.Name)"
    } else {
        throw "Brak w bundlu: $($check.Name) [$($check.Path)]"
    }
}

$target = Join-Path $PSScriptRoot "dist\regis-satellite"
Write-Host ""
Write-Host "Gotowe: $target" -ForegroundColor Green
Write-Host "Instalacja lokalna:         .\install.ps1"
Write-Host "Szybki test bez instalacji: dist\regis-satellite\regis-satellite.exe"
Write-Host ""
Write-Host "Uwaga: ikona pojawia sie w zasobniku, okna nie ma. Logi: %APPDATA%\Regis\logs\satellite.log" -ForegroundColor Yellow
