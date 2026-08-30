"""Wersja produktu Regis — jedyne źródło prawdy w całym monorepo.

Do tej pory `0.1.0` było wpisane ręcznie w pięciu miejscach (`shared/__init__.py`,
`server/__init__.py`, `config/settings.json`, tytuł aplikacji FastAPI, plus trzy
`pyproject.toml`), a repozytorium nie miało ani jednego tagu — nie dało się
powiedzieć, którą wersję ma uruchomiony serwer. Od teraz wszystko, co pokazuje
wersję w czasie działania, czyta ją stąd:

* log startowy serwera (`server/main.py`),
* `GET /api/v1/health` i tytuł OpenAPI,
* tag obrazu Dockera (`REGIS_VERSION` w `docker-compose.yml`),
* metadane buildu satelity desktopowej.

**Wersje w `pyproject.toml` są celowo nieruszane** — to wersje *pakietów*, których
nikt nie publikuje ani nie instaluje po numerze. Wersją *produktu* jest ta stała.

Cykl wydania (pełny runbook: `docs/onboarding.md`, sekcja „Wydanie"):
podnieś `__version__` -> wpis w `CHANGELOG.md` -> commit -> `git tag -a v<wersja>`.
"""

__version__ = "0.2.0"
"""Wersja produktu wg SemVer, bez prefiksu `v` (tag gita ma prefiks: `v0.2.0`)."""
