@echo off
setlocal enabledelayedexpansion

:: Zmiana katalogu roboczego na główny katalog projektu
cd /d "%~dp0.."

echo ====================================
echo Regis - Narzedzia Deweloperskie
echo ====================================
echo.

set count=0
for %%F in (tools\*.py) do (
    set /a count+=1
    set "script[!count!]=%%F"
    echo [!count!] %%~nxF
)

if %count%==0 (
    echo Brak skryptow Pythona w folderze tools.
    pause
    exit /b
)

echo.
set /p choice="Wybierz numer skryptu do uruchomienia: "

if not defined script[%choice%] (
    echo Nieprawidlowy wybor.
    pause
    exit /b
)

set target=!script[%choice%]!
echo.
echo Uruchamianie %target%...
echo ------------------------------------
python "%target%"
echo ------------------------------------
pause
