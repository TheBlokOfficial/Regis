# -*- mode: python ; coding: utf-8 -*-
"""Specyfikacja PyInstallera dla satelity desktopowej.

Budowanie: `build.ps1` (Windows) albo `build.sh` (Linux) — nie wołaj `pyinstaller`
wprost. Skrypty dobierają interpreter (zarządzany przez uv, nie systemowy — patrz
komentarz w `build.ps1`), budują w osobnym środowisku i sprawdzają gotowy bundel.

**Czego tu celowo NIE ma.** Pierwsza wersja tego pliku wołała
`collect_dynamic_libs("sounddevice")`, żeby dołączyć bibliotekę PortAudio. To było
wywołanie puste — PyInstaller zgłasza wtedy
`skipping library collection for module 'sounddevice' as it is not a package`,
bo `sounddevice` to pojedynczy moduł, a PortAudio mieszka w osobnym pakiecie danych
`_sounddevice_data`. Prawdziwą robotę wykonuje gotowy hook
`_pyinstaller_hooks_contrib/stdhooks/hook-sounddevice.py`, i to jemu ją zostawiamy.
Zamiast martwego wywołania **skrypty budujące sprawdzają obecność PortAudio w gotowym
bundlu** — bo jego brak nie wywala builda, tylko gotową aplikację, i to dopiero przy
próbie otwarcia mikrofonu (czyli po pierwszym wake-wordzie).

Tak samo backend `pystray` (`_win32`/`_xorg`/`_appindicator`, wybierany dynamicznie po
platformie) dobiera `hook-pystray.py` z tego samego zestawu. Wpisywanie ich ręcznie
w `hiddenimports` groziłoby wywaleniem builda na Linuksie o backend, którego na danej
maszynie nie ma.

`--onedir`, nie `--onefile`: onefile rozpakowuje PortAudio i numpy do katalogu
tymczasowego przy KAŻDYM starcie (sekundy opóźnienia dla aplikacji, która ma wstawać
razem z systemem) i częściej wywołuje fałszywe alarmy antywirusa.

`console=False`: brak okna terminala. Konsekwencja rozbrojona osobno — `setup_logging()`
pomija handler konsoli, gdy `sys.stdout` jest `None` (patrz `shared/logging.py`),
inaczej pierwszy log zabijałby aplikację bez śladu.
"""

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ["src/desktop_satellite/main.py"],
    pathex=["src", "../../packages/shared/src"],
    binaries=[],
    datas=[],
    # Moduły satelity ładowane leniwie (`tray.py` importowany dopiero w trybie
    # zasobnika, backendy autostartu po platformie) — statyczna analiza ich nie widzi.
    hiddenimports=collect_submodules("desktop_satellite"),
    hookspath=[],
    runtime_hooks=[],
    # Wycięte świadomie: satelita nie rysuje wykresów, nie serwuje HTTP i nie uruchamia
    # modeli — wake-word liczy serwer. Każda z tych bibliotek dokłada dziesiątki
    # megabajtów do katalogu, który kopiuje się na inne maszyny.
    excludes=["matplotlib", "tkinter", "fastapi", "uvicorn", "starlette", "onnxruntime"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="regis-satellite",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="regis-satellite",
)
