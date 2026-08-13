# shared

Paczka ze wspólnym kodem infrastrukturalnym dla usług monorepo Regis. Nie posiada zależności od konkretnych usług — jedyna zależność zewnętrzna to `pydantic`.

Zawartość:
- **`config.py`** — `ConfigStore`: generyczna, silnie typowana persystencja modeli Pydantic w plikach JSON (używana dla ustawień serwera, backendów LLM, promptów, sesji, integracji i grup urządzeń). Dodatkowo `get_service_root()` (odnajdywanie korzenia usługi po `pyproject.toml`) oraz `sanitize_identifier()` (walidacja identyfikatorów używanych jako nazwy plików — ochrona przed directory traversal).
- **`event_bus.py`** — `EventBus`: asynchroniczna magistrala pub/sub (`subscribe`/`unsubscribe`/`publish`, wsparcie dla subskrypcji `*`) wraz z generyczną kopertą `Event[T]`.
- **`contracts.py`** — DTO współdzielone przez serwer i konsolę WWW: status systemu, dostawcy LLM i generyczne schematy ich opcji, czat i sesje, prompty systemowe oraz integracje i grupy urządzeń.
- **`logging.py`** — `setup_logging()` / `get_logger()`: jednolita konfiguracja logów z konwencją nazw kategorii (`regis.main`, `regis.agent`, …).

Pełny opis architektury i lista DTO wg grup: [`docs/manifest.md`](../../docs/manifest.md) (sekcja 3.6).
