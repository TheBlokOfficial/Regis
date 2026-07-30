# RFC: Auto-Discovery (Zero-Conf) i Generowanie Konfiguracji

## 1. Opis Problemu
W miarę jak architektura Regis staje się coraz bardziej rozproszona, proces wdrażania Węzłów Roboczych (Workers) oraz Satelitów napotkał na barierę zwaną "hardkodowaniem". Obecnie każde urządzenie peryferyjne musi ręcznie otrzymać statyczny adres IP Kontrolera (Malinki) w swoim pliku środowiskowym lub profilu JSON (`controller_url`). 
Jeśli router zmieni adres IP Kontrolera (np. z powodu wygaśnięcia dzierżawy DHCP lub przemieszczenia sprzętu), wszystkie satelity i węzły tracą z nim łączność, wymuszając ręczną rekonfigurację każdego urządzenia. Dodatkowo manualne budowanie plików `.env` i `.json` przez użytkownika po każdej kompilacji spowalnia instalację "Plug-and-Play".

## 2. Proponowane Rozwiązanie: UDP Broadcast (Regis-Radar)
Aby zachować minimalizm technologiczny projektu (bez instalowania "ciężkich" paczek jak `zeroconf`/mDNS, które na Windowsie często sprawiają problemy), projekt wdroży własny, ekstremalnie lekki protokół oparty na sieciowych gniazdach UDP.

### Jak to ma działać:
1. **Po stronie Kontrolera:** 
   Malinka uruchamia w tle osobny wątek z serwerem UDP (np. na porcie 8002). Serwer ten w nieskończoność nasłuchuje pakietów.
2. **Po stronie Satelity/Workera:** 
   Po ustawieniu parametru `"controller_url": "auto"`, urządzenie startując wysyła bezkierunkowy okrzyk w sieć lokalną (Broadcast): `"REGIS_DISCOVERY_PING"`.
3. **Zestawienie:**
   Kontroler odbiera pakiet i odsyła bezpośrednio nadawcy swój pełny, bieżący adres HTTP API (np. `http://192.168.0.120:8000`). Zależność zostaje zawiązana, a urządzenie peryferyjne automatycznie przechodzi do rejestracji.

## 3. Auto-Generowanie Plików Startowych
Wraz z protokołem Zero-Conf ulepszony zostanie skrypt `scripts/build_windows.bat`. Zamiast kopiować pusty wzorzec, skrypt za pomocą komend `echo` wygeneruje od razu gotowe pliki:
- Plik `.env` z wpisanym już statycznie `ACTIVE_PROFILE=[rola]`.
- Plik w folderze `data/settings.[rola].json` posiadający już wpisane `"controller_url": "auto"`.

## 4. Wymagane Kroki Implementacyjne
1. Stworzenie `core/discovery.py` z dwiema funkcjami (`start_discovery_server` i `discover_controller`).
2. Modyfikacja `lifespan` w `apps/controller/main.py`.
3. Modyfikacja ładowania zmiennych startowych w `apps/worker/server.py` i innych węzłach.
4. Aktualizacja skryptu `scripts/build_windows.bat` o funkcje auto-generujące pliki.
