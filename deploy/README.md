# Wdrożenie serwera Regis

Cel: **Raspberry Pi 5, Raspberry Pi OS Lite 64-bit, headless.** Obraz budowany
**natywnie na Pi** — bez QEMU i bez rejestru obrazów, więc aktualizacja to jedno
polecenie. Przeniesienie na mini-PC z Linuksem (amd64) nie wymaga żadnej zmiany
w `Dockerfile`, tylko rebuildu na tamtej maszynie.

Architektura wdrożenia w jednym zdaniu: kontener działa w **sieci hosta**, dane
i konfiguracja leżą na hoście jako zwykłe pliki, klucze API przychodzą ze środowiska.

---

## 1. Pierwsza instalacja

### 1.1. Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
```

Wyloguj się i zaloguj ponownie, żeby przynależność do grupy zadziałała. Sprawdź:

```bash
docker compose version
```

Wymagane **Compose ≥ 2.24** — `docker-compose.yml` używa `env_file: required: false`.

### 1.2. Repozytorium

```bash
git clone <adres-repozytorium> ~/regis && cd ~/regis
git checkout "$(git tag --list 'v*' --sort=-v:refname | head -n1)"
```

### 1.3. Katalogi danych

Kontener działa jako użytkownik o **uid 1000**, czyli pierwszym użytkowniku
Raspberry Pi OS — bind-mounty są więc zapisywalne bez `chown`. Jeśli wdrażasz
jako inny użytkownik, dopasuj właściciela.

```bash
mkdir -p data config
```

Oba katalogi są w `.gitignore`, więc `git pull` nigdy ich nie dotknie.

### 1.4. Konfiguracja i klucze

```bash
cp .env.example .env
nano .env
```

Wypełnij zmienne z kluczami API i ustaw `REGIS_PORT`, jeśli 8000 jest zajęty.
Same klucze **nie trafiają do plików konfiguracyjnych** — w Web UI wpisujesz
w polu klucza `env:NAZWA_ZMIENNEJ`, a wartość przychodzi stąd (patrz
`packages/shared/src/shared/secrets.py`). Dzięki temu `data/` można kopiować
i wersjonować bez ryzyka wyniesienia sekretów.

### 1.5. Model wake-word

**Krok łatwy do pominięcia i cichy w skutkach.** `data/wakeword/regis.onnx` jest
gitignorowany, więc nie przyjeżdża z repozytorium. Bez niego serwer nie zgłasza
błędu — degraduje się do placeholdera progu amplitudy, czyli wake-word „działa",
tylko reaguje na każdy głośniejszy dźwięk.

Z maszyny, gdzie model leży:

```bash
scp data/wakeword/regis.onnx pi@raspberrypi.local:~/regis/data/wakeword/
```

`deploy.sh` ostrzega, jeśli pliku nie ma.

### 1.6. Start

```bash
docker compose build
docker compose up -d
docker compose logs -f
```

Web UI: `http://<adres-pi>:8000`. Konfiguracja dostawców, świata i klientów
odbywa się tam — nie przez pliki.

---

## 2. Aktualizacja

```bash
./deploy/deploy.sh            # najnowszy tag
./deploy/deploy.sh v0.3.0     # konkretna wersja
./deploy/deploy.sh master     # czubek gałęzi (do testów)
```

Skrypt sprawdza warunki wstępne, przełącza repozytorium, buduje obraz z tagiem
równym `shared.__version__`, podmienia kontener i **czeka na `/api/v1/health`** —
przy braku odpowiedzi w 60 s kończy się błędem i pokazuje logi.

Wycofanie zmiany to ta sama komenda z poprzednim tagiem: `./deploy/deploy.sh v0.2.0`.

---

## 3. Kopia zapasowa

Cały stan mieszka w dwóch katalogach na hoście:

```bash
tar czf regis-backup-$(date +%F).tar.gz data config .env
```

`data/` to sesje, presety dostawców, konfiguracja świata, telemetria i logi;
`config/` to `settings.json`; `.env` to klucze. Odtworzenie: rozpakuj i `docker compose up -d`.

---

## 4. Dlaczego sieć hosta

`server/discovery.py` rozgłasza obecność serwera przez UDP `<broadcast>`, dzięki
czemu satelity znajdują go **bez żadnej konfiguracji po swojej stronie**. Broadcast
z sieci bridge nie wychodzi do LAN-u, więc `network_mode: host` jest tu warunkiem
koniecznym, nie optymalizacją. Konsekwencje:

* `ports:` w `docker-compose.yml` byłoby ignorowane — port bierze się wyłącznie
  z `REGIS_PORT` albo z `config/settings.json`;
* na Docker Desktop (Windows/macOS) sieć hosta nie działa tak samo — tam każda
  satelita wymagałaby jawnego `--server-url`.

---

## 5. Diagnostyka

| Objaw | Gdzie patrzeć |
| :--- | :--- |
| Kontener nie wstaje | `docker compose logs --tail=100` |
| Satelita nie znajduje serwera | Czy `network_mode: host` jest aktywne (`docker inspect regis-server \| grep NetworkMode`); czy Pi i satelita są w tej samej podsieci |
| Wake-word reaguje na wszystko | Brak `data/wakeword/regis.onnx` — log startowy mówi wtedy o placeholderze |
| Dostawca zwraca błąd autoryzacji | Zmienna z `.env` nie dotarła: `docker compose exec server printenv \| grep REGIS_` |
| Puste sesje / brak presetów po aktualizacji | Wolumen nie jest podmontowany — `docker inspect regis-server \| grep -A5 Mounts` |
| Szczegóły wywołań modelu | Web UI → zakładka **Logi** (telemetria) oraz `data/logs/regis.log` |

Wersja działającego serwera: `curl -s http://127.0.0.1:8000/api/v1/health`.
