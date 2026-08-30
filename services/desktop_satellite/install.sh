#!/usr/bin/env bash
#
# Instalacja zbudowanej satelity na tym komputerze (Linux).
#
#     ./install.sh              # instaluje i uruchamia
#     ./install.sh --no-start   # tylko kopiuje pliki
#
# Kopiuje dist/regis-satellite/ do ~/.local/share/regis, tworzy wpis w menu aplikacji
# i — jeśli istnieje lokalna konfiguracja ze źródeł — przenosi sender_id, żeby nie
# trzeba było rejestrować satelity od nowa.
#
# Autostartu NIE włącza: to przełącznik w menu zasobnika, świadoma decyzja użytkownika
# (patrz autostart.py).

set -euo pipefail
cd "$(dirname "$0")"

log() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mBŁĄD: %s\033[0m\n' "$*" >&2; exit 1; }

SOURCE="$(pwd)/dist/regis-satellite"
[[ -d "$SOURCE" ]] || die "Brak $SOURCE — uruchom najpierw ./build.sh"

TARGET="$HOME/.local/share/regis"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/regis"

log "Zatrzymywanie działającej instancji"
pkill -f "$TARGET/regis-satellite" 2>/dev/null || true

log "Kopiowanie do $TARGET"
rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -r "$SOURCE/." "$TARGET/"

# Wersja zainstalowana trzyma konfigurację w ~/.config/regis, a uruchomienie ze
# źródeł w services/desktop_satellite/config. To dwie różne lokalizacje, więc bez
# przeniesienia sender_id nowa instalacja dostałaby nowy UUID i wypadła z rejestru
# klientów w Web UI (patrz config.py).
if [[ -f config/settings.json && ! -f "$CONFIG_DIR/settings.json" ]]; then
  log "Przenoszenie dotychczasowego sender_id"
  mkdir -p "$CONFIG_DIR"
  cp config/settings.json "$CONFIG_DIR/settings.json"
fi

log "Wpis w menu aplikacji"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/regis-satellite.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Regis Satellite
Comment=Satelita głosowa Regis
Exec=$TARGET/regis-satellite
Terminal=false
Categories=Utility;AudioVideo;
EOF

printf '\n\033[32mZainstalowano w %s\033[0m\n' "$TARGET"
printf 'Konfiguracja: %s\n' "$CONFIG_DIR"
printf 'Logi:         %s/logs/satellite.log\n\n' "$CONFIG_DIR"
printf 'Dalsze kroki:\n'
printf '  1. Uruchom aplikację — ikona pojawi się w zasobniku.\n'
printf '  2. Z menu ikony skopiuj sender_id.\n'
printf '  3. W Web UI serwera: Ustawienia -> Klienci -> zatwierdź nadawcę i przypisz pokój.\n'
printf "  4. W menu ikony włącz 'Uruchamiaj przy starcie systemu', jeśli tego chcesz.\n"

if [[ "${1:-}" != "--no-start" ]]; then
  log "Uruchamianie"
  nohup "$TARGET/regis-satellite" >/dev/null 2>&1 &
  disown
fi
