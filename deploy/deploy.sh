#!/usr/bin/env bash
#
# Aktualizacja serwera Regis na maszynie docelowej (Raspberry Pi 5 / dowolny Linux).
# Pierwsza instalacja: patrz deploy/README.md — ten skrypt zakłada, że repozytorium,
# `.env`, `data/` i `config/` już istnieją.
#
#   ./deploy/deploy.sh            # wdraża najnowszy tag
#   ./deploy/deploy.sh v0.2.0     # wdraża konkretną wersję
#   ./deploy/deploy.sh master     # wdraża czubek gałęzi (do testów, nie na produkcję)

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

log() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mBŁĄD: %s\033[0m\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------------------
# 1. Warunki wstępne — sprawdzane zawczasu, żeby nie zatrzymać się w połowie
# ------------------------------------------------------------------------------
command -v docker >/dev/null || die "Nie znaleziono dockera."
docker compose version >/dev/null 2>&1 || die "Nie znaleziono wtyczki 'docker compose'."
[[ -f .env ]] || die "Brak pliku .env. Skopiuj .env.example i uzupełnij (patrz deploy/README.md)."

# Model wake-word jest gitignorowany, więc NIE przyjeżdża z repozytorium. Jego brak
# nie jest błędem krytycznym — serwer degraduje się wtedy do placeholdera progu
# amplitudy — ale jest to degradacja cicha, więc mówimy o niej głośno.
[[ -f data/wakeword/regis.onnx ]] || \
  printf '\033[33mUWAGA: brak data/wakeword/regis.onnx — wake-word zejdzie do placeholdera amplitudy.\033[0m\n'

# ------------------------------------------------------------------------------
# 2. Wybór wersji
# ------------------------------------------------------------------------------
log "Pobieranie zmian"
git fetch --tags --prune

TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  TARGET="$(git tag --list 'v*' --sort=-v:refname | head -n1)"
  [[ -n "$TARGET" ]] || die "Repozytorium nie ma żadnego tagu v*. Podaj wersję jawnie: ./deploy/deploy.sh master"
fi

log "Przełączanie na: $TARGET"
git -c advice.detachedHead=false checkout --quiet "$TARGET"
git pull --quiet --ff-only 2>/dev/null || true   # gałąź tak, tag nie ma czego ciągnąć

# Tag obrazu bierzemy z JEDYNEGO źródła prawdy o wersji, nie z nazwy gałęzi.
REGIS_VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' packages/shared/src/shared/version.py)"
[[ -n "$REGIS_VERSION" ]] || die "Nie udało się odczytać wersji z packages/shared/src/shared/version.py"
export REGIS_VERSION
log "Wersja produktu: $REGIS_VERSION"

# ------------------------------------------------------------------------------
# 3. Budowa i podmiana
# ------------------------------------------------------------------------------
log "Budowanie obrazu (natywnie, bez QEMU — na Pi potrwa)"
docker compose build

log "Restart usługi"
docker compose up -d

# ------------------------------------------------------------------------------
# 4. Weryfikacja — deploy bez sprawdzenia to nie deploy
# ------------------------------------------------------------------------------
# Port z .env, jeśli go tam ustawiono. Bez odwołań wstecznych w sed — zdejmujemy
# wszystko przed '=' i zostawiamy same cyfry, więc cudzysłowy i spacje nie przeszkadzają.
PORT="$(grep -E '^[[:space:]]*REGIS_PORT[[:space:]]*=' .env | tail -n1 | sed -e 's/.*=//' -e 's/[^0-9]//g')"
PORT="${PORT:-8000}"

log "Czekam na healthcheck (http://127.0.0.1:$PORT/api/v1/health)"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1; then
    printf '\033[32mSerwer odpowiada:\033[0m '
    curl -fsS "http://127.0.0.1:$PORT/api/v1/health"
    printf '\n'
    log "Ostatnie logi"
    docker compose logs --tail=20
    exit 0
  fi
  sleep 2
done

printf '\033[31mSerwer nie odpowiedział w 60 s. Logi:\033[0m\n' >&2
docker compose logs --tail=60 >&2
exit 1
