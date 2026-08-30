#!/usr/bin/env bash
#
# Budowa satelity desktopowej dla Linuksa.
#
#     ./build.sh
#
# Wynik: dist/regis-satellite/ — katalog gotowy do skopiowania na maszynę docelową
# albo do zainstalowania lokalnie przez ./install.sh.

set -euo pipefail
cd "$(dirname "$0")"

# DOKŁADNA wersja, nie "3.13": `uv python find` dopasowuje pierwszy pasujący interpreter,
# a to bywa Python systemowy albo conda. Pełny numer jest jedynym sposobem, żeby trafić
# w interpreter zarządzany przez uv.
PYTHON_VERSION="3.13.15"

log() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mBŁĄD: %s\033[0m\n' "$*" >&2; exit 1; }

log "Interpreter zarządzany przez uv ($PYTHON_VERSION)"
# Budujemy samodzielnym interpreterem uv, nie tym, co deweloper ma w PATH. Powód jest
# praktyczny, nie estetyczny: build zrobiony przez `uv run` na współdzielonym `.venv`
# tego monorepo dał aplikację, która padała przy starcie na
# "DLL load failed while importing _ssl" — do bundla trafił niespójny komplet bibliotek
# OpenSSL. Interpreter uv jest kompletny, taki sam na każdej maszynie i niezależny od
# tego, co deweloper ma zainstalowane obok.
python -m uv python install "$PYTHON_VERSION"
INTERPRETER="$(python -m uv python find --managed-python "$PYTHON_VERSION" | head -n1)"
[[ -n "$INTERPRETER" ]] || die "Nie znaleziono interpretera zarządzanego $PYTHON_VERSION."
printf '    %s\n' "$INTERPRETER"

log "Zależności buildu (osobne środowisko .venv-build)"
# WŁASNE środowisko, nie główne `.venv`: to monorepo `uv workspace`, więc
# `uv sync --package desktop_satellite` przestawiłoby wspólne `.venv` na same zależności
# satelity i zostawiło środowisko serwera niesprawne aż do kolejnego `uv sync`.
# Build nie ma prawa psuć środowiska deweloperskiego.
export UV_PROJECT_ENVIRONMENT="$(pwd)/.venv-build"
rm -rf .venv-build
python -m uv sync --package desktop_satellite --group build --python "$INTERPRETER"

log "Czyszczenie poprzedniego buildu"
rm -rf dist build

log "PyInstaller (--onedir, --noconsole)"
# Wprost z .venv-build, nie przez `uv run` — patrz komentarz o interpreterze wyżej.
./.venv-build/bin/pyinstaller regis-satellite.spec --noconfirm

log "Weryfikacja bundla"
# Brak PortAudio nie wywala BUILDA, tylko GOTOWĄ aplikację, i to nie od razu: dopiero
# przy próbie otwarcia mikrofonu, czyli po pierwszym wake-wordzie. Sprawdzamy tutaj,
# żeby nie dowiedzieć się o tym na maszynie docelowej.
INTERNAL="dist/regis-satellite/_internal"
if compgen -G "$INTERNAL/_sounddevice_data/portaudio-binaries/*" > /dev/null; then
  printf '    OK  PortAudio (mikrofon)\n'
else
  die "Brak PortAudio w bundlu ($INTERNAL/_sounddevice_data/portaudio-binaries/)."
fi

printf '\n\033[32mGotowe: %s/dist/regis-satellite\033[0m\n' "$(pwd)"
printf 'Instalacja lokalna:         ./install.sh\n'
printf 'Szybki test bez instalacji:  dist/regis-satellite/regis-satellite\n\n'
printf '\033[33mUwaga: ikona pojawia się w zasobniku, okna nie ma. Logi: ~/.config/regis/logs/satellite.log\033[0m\n'
printf '\033[33mŚrodowisko graficzne musi obsługiwać ikony zasobnika (GNOME wymaga rozszerzenia AppIndicator).\033[0m\n'
