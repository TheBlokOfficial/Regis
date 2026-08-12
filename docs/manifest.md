# Manifest Projektu Regis

## 1. Cel
System usług rozproszonych komunikujących się po sieci lokalnej.

## 2. Architektura Monorepo
- **`services/`** – niezależne usługi sieciowe (każda posiada własny kod `src/`, konfigurację i zależności).
- **`packages/`** – wspólne biblioteki i kontrakty sieciowe (DTO, typy, helpery).

## 3. Stos Technologiczny i Zasady
- **Język**: Python 3.11+
- **Zarządzanie zależnościami**: `uv` (`uv workspace`)
- **Komunikacja**: WebSockets / REST (FastAPI)
- **Typowanie**: Obowiązkowe adnotacje typów (Strict Type Hints)
