"""Jakie parametry rozumie konkretny model — i skąd wziąć listę modeli.

**Dlaczego to w ogóle istnieje.** Do tej pory preset LLM miał trzy pola (model, klucz,
`max_tokens`) wspólne dla wszystkich dostawców, a jedyny parametr generacji w systemie
(`reasoning: {"effort": "none"}` dla OpenRoutera) był **zahardkodowany w fabryce** — więc
dokładnie ta rzecz, którą chce się stroić per model, była nietykalna. Problem jest realny
i nie da się go rozwiązać jedną wspólną listą pól: `reasoning_effort` istnieje dla
gpt-oss, nie istnieje dla llamy, a dla Qwena ma **inny zestaw wartości** niż dla gpt-oss.

**Trzy dostawcy, trzy różne źródła prawdy** (świadomy wybór, nie niespójność):

* **OpenRouter** — jedyny, który sam mówi, co wspiera: `GET /api/v1/models` zwraca
  `supported_parameters` per model. Formularz budujemy z tego, więc nie gnije.
* **Groq** — lista modeli na żywo (`/openai/v1/models`, format OpenAI), ale parametry
  z tabeli poniżej: Groq nie eksponuje ich w API, a jest ich garść i są udokumentowane.
* **Ollama** — lista z `/api/tags` (to, co użytkownik ma realnie pobrane lokalnie),
  parametry wspólne dla Ollamy + podpowiedzi per rodzina modelu.

Wartości i nazwy pól zweryfikowane w dokumentacji dostawców (Groq: `reasoning_effort`
`low`/`medium`/`high` dla gpt-oss i `none`/`default` dla Qwena, `include_reasoning`
wykluczające się z `reasoning_format`; Ollama: `think` przyjmujące bool albo
`low`/`medium`/`high`/`max`) — nie zgadywane.

**Lista modeli nigdy nie zamyka wyboru.** Każdy typ pozwala wpisać identyfikator z ręki
(`fallback_options_schema`) — nowy model pojawia się u dostawcy wcześniej, niż ktokolwiek
zdąży zaktualizować ten plik.
"""

from __future__ import annotations

from typing import Any, Iterable

import httpx
from shared import ModelSpecDTO, ProviderOptionChoice, ProviderOptionSpec, get_logger

from server.ai.llm.models import BackendInstanceConfig, ProviderType

logger = get_logger("regis.ai.llm.model_catalog")

_DISCOVERY_TIMEOUT_SECONDS = 8.0


# --------------------------------------------------------------------------
# Parametry wspólne — rozumie je każdy dostawca w tym projekcie
# --------------------------------------------------------------------------


def _number(name: str, label: str, default: str | None, hint: str, placeholder: str | None = None) -> ProviderOptionSpec:
    return ProviderOptionSpec(
        name=name,
        label=label,
        type="number",
        required=False,
        default_value=default,
        placeholder=placeholder or default,
        hint=hint,
    )


def _enum(name: str, label: str, values: Iterable[tuple[str, str]], default: str | None, hint: str) -> ProviderOptionSpec:
    return ProviderOptionSpec(
        name=name,
        label=label,
        type="enum",
        required=False,
        default_value=default,
        choices=[ProviderOptionChoice(value=value, label=text) for value, text in values],
        hint=hint,
    )


def _bool(name: str, label: str, default: str, hint: str) -> ProviderOptionSpec:
    """Wartość logiczna jest wyrażana jako `enum` z dwiema opcjami, nie osobnym typem
    pola: projekt świadomie nie używa natywnych checkboxów przeglądarki, więc i tak
    renderowałaby się jako ten sam custom-select co reszta list wyboru."""
    return _enum(name, label, [("true", "Tak"), ("false", "Nie")], default, hint)


def _common_params() -> list[ProviderOptionSpec]:
    return [
        _number("max_tokens", "Limit tokenów wyjściowych", "4096", "Twardy sufit długości odpowiedzi."),
        _number("temperature", "Temperatura", None, "0 = powtarzalnie, 1+ = kreatywnie. Puste = domyślna modelu.", "0.7"),
        _number("top_p", "Top-p", None, "Odcięcie prawdopodobieństwa. Zwykle strojone zamiast temperatury, nie razem.", "1.0"),
    ]


# --------------------------------------------------------------------------
# GROQ — lista na żywo, parametry z tabeli rodzin (Groq nie podaje ich w API)
# --------------------------------------------------------------------------

_GPT_OSS_PARAMS = [
    _enum(
        "reasoning_effort",
        "Głębokość rozumowania",
        [("low", "Niska"), ("medium", "Średnia"), ("high", "Wysoka")],
        None,
        "Ile tokenów model przeznaczy na myślenie, zanim odpowie.",
    ),
    _bool(
        "include_reasoning",
        "Zwracaj rozumowanie",
        "true",
        "Wyłączone = model nadal myśli, ale nie przysyła śladu. Regis pokazuje go w czacie i pomija w mowie.",
    ),
]

_QWEN_GROQ_PARAMS = [
    _enum(
        "reasoning_effort",
        "Rozumowanie",
        [("none", "Wyłączone"), ("default", "Domyślne")],
        None,
        "Qwen na Groq przyjmuje tu inne wartości niż gpt-oss — stąd osobny wpis w tabeli.",
    ),
    _enum(
        "reasoning_format",
        "Format rozumowania",
        [("parsed", "Osobne pole"), ("raw", "W treści"), ("hidden", "Ukryte")],
        "parsed",
        "Regis oczekuje osobnego pola. 'raw' wkleja rozumowanie w treść odpowiedzi i jest niezgodne z narzędziami.",
    ),
]


def _groq_params_for(model_id: str) -> list[ProviderOptionSpec]:
    lowered = model_id.lower()
    if "gpt-oss" in lowered:
        return _common_params() + _GPT_OSS_PARAMS
    if "qwen" in lowered:
        return _common_params() + _QWEN_GROQ_PARAMS
    return _common_params()


# --------------------------------------------------------------------------
# OPENROUTER — formularz wprost z `supported_parameters` modelu
# --------------------------------------------------------------------------

_OPENROUTER_PARAM_BUILDERS: dict[str, ProviderOptionSpec] = {
    "temperature": _number("temperature", "Temperatura", None, "0 = powtarzalnie, 1+ = kreatywnie.", "0.7"),
    "top_p": _number("top_p", "Top-p", None, "Odcięcie prawdopodobieństwa.", "1.0"),
    "top_k": _number("top_k", "Top-k", None, "Ile najlepszych tokenów brać pod uwagę.", "40"),
    "frequency_penalty": _number("frequency_penalty", "Kara za częstość", None, "Zniechęca do powtarzania tych samych słów.", "0"),
    "presence_penalty": _number("presence_penalty", "Kara za obecność", None, "Zniechęca do wracania do tych samych tematów.", "0"),
    "repetition_penalty": _number("repetition_penalty", "Kara za powtórzenia", None, "Wariant powyższych używany przez modele otwarte.", "1.0"),
    "reasoning_effort": _enum(
        "reasoning_effort",
        "Głębokość rozumowania",
        [("none", "Wyłączone"), ("low", "Niska"), ("medium", "Średnia"), ("high", "Wysoka")],
        None,
        "Puste = domyślna modelu. Wcześniej Regis wymuszał tu 'none' dla każdego modelu OpenRoutera.",
    ),
}


def _openrouter_params_for(supported: list[str]) -> list[ProviderOptionSpec]:
    """Bierzemy WYŁĄCZNIE te parametry, które Regis realnie umie wysłać — `supported_parameters`
    wymienia też rzeczy w rodzaju `logit_bias` czy `web_search_options`, których ten projekt
    nie obsługuje i pokazywanie ich w formularzu byłoby obietnicą bez pokrycia."""
    params = [_number("max_tokens", "Limit tokenów wyjściowych", "4096", "Twardy sufit długości odpowiedzi.")]
    for key in supported:
        spec = _OPENROUTER_PARAM_BUILDERS.get(key)
        if spec is not None and all(existing.name != spec.name for existing in params):
            params.append(spec)
    return params


# --------------------------------------------------------------------------
# OLLAMA — parametry wspólne + podpowiedzi per rodzina
# --------------------------------------------------------------------------

_OLLAMA_BASE_PARAMS = [
    _number("num_predict", "Limit tokenów wyjściowych", "4096", "Odpowiednik max_tokens po stronie Ollamy."),
    _number("num_ctx", "Okno kontekstu", None, "Puste = wartość z Modelfile. Zwiększenie kosztuje RAM/VRAM.", "8192"),
    _number("temperature", "Temperatura", None, "0 = powtarzalnie, 1+ = kreatywnie.", "0.7"),
    _number("top_p", "Top-p", None, "Odcięcie prawdopodobieństwa.", "0.9"),
    _number("top_k", "Top-k", None, "Ile najlepszych tokenów brać pod uwagę.", "40"),
    _number("repeat_penalty", "Kara za powtórzenia", None, "Powyżej 1.0 zniechęca do zapętlania się.", "1.1"),
]

_OLLAMA_THINK_PARAM = _enum(
    "think",
    "Tryb myślenia",
    [("off", "Wyłączone"), ("on", "Włączone"), ("low", "Niski"), ("medium", "Średni"), ("high", "Wysoki"), ("max", "Maksymalny")],
    None,
    "Dotyczy wyłącznie modeli myślących (qwen3, deepseek-r1, gpt-oss). Puste = zachowanie domyślne modelu.",
)

# Rodziny, o których wiadomo, że wspierają `think` — dopasowanie po nazwie modelu ALBO
# po `details.family` z `/api/tags`. To podpowiedź, nie zamknięta lista: parametr i tak
# można ustawić przy modelu wpisanym z ręki.
_OLLAMA_THINKING_FAMILIES = ("qwen3", "qwq", "deepseek-r1", "gpt-oss", "magistral", "cogito")


def _ollama_params_for(model_id: str, family: str = "") -> list[ProviderOptionSpec]:
    haystack = f"{model_id} {family}".lower()
    if any(marker in haystack for marker in _OLLAMA_THINKING_FAMILIES):
        return _OLLAMA_BASE_PARAMS + [_OLLAMA_THINK_PARAM]
    return list(_OLLAMA_BASE_PARAMS)


# --------------------------------------------------------------------------
# Formularz dla modelu wpisanego z ręki (spoza listy)
# --------------------------------------------------------------------------


def fallback_options_schema(provider_type: ProviderType) -> list[ProviderOptionSpec]:
    if provider_type == ProviderType.OLLAMA:
        return _OLLAMA_BASE_PARAMS + [_OLLAMA_THINK_PARAM]
    if provider_type == ProviderType.GROQ:
        return _common_params() + _GPT_OSS_PARAMS
    return _common_params() + [_OPENROUTER_PARAM_BUILDERS["reasoning_effort"]]


# --------------------------------------------------------------------------
# Odkrywanie modeli na żywo
# --------------------------------------------------------------------------


async def discover_models(config: BackendInstanceConfig) -> tuple[list[ModelSpecDTO], str | None]:
    """Zwraca `(modele, powód_pustej_listy)`. Nigdy nie rzuca — brak klucza czy padnięty
    serwer Ollamy to normalny stan konfiguracyjny, nie błąd aplikacji; UI pokazuje powód
    i pozwala wpisać model z ręki."""
    try:
        if config.type == ProviderType.OPENROUTER:
            return await _discover_openrouter()
        if config.type == ProviderType.GROQ:
            return await _discover_groq(config.options.get("api_key", ""))
        if config.type == ProviderType.OLLAMA:
            return await _discover_ollama(config.options.get("base_url", "http://localhost:11434"))
    except httpx.HTTPError as err:
        logger.warning(f"Nie udało się pobrać listy modeli [{config.type.value}]: {err}")
        return [], "Nie udało się połączyć z dostawcą — wpisz identyfikator modelu ręcznie."
    except Exception as err:
        logger.error(f"Błąd odkrywania modeli [{config.type.value}]: {err}")
        return [], "Nie udało się pobrać listy modeli — wpisz identyfikator modelu ręcznie."
    return [], None


async def _discover_openrouter() -> tuple[list[ModelSpecDTO], str | None]:
    """Katalog OpenRoutera jest publiczny — nie wymaga klucza, więc lista modeli działa
    także w świeżym, jeszcze nieskonfigurowanym presecie."""
    async with httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT_SECONDS) as client:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        payload = response.json()

    models = [
        ModelSpecDTO(
            id=entry["id"],
            label=entry.get("name") or entry["id"],
            options_schema=_openrouter_params_for(entry.get("supported_parameters") or []),
        )
        for entry in payload.get("data", [])
        if entry.get("id")
    ]
    models.sort(key=lambda m: m.label.lower())
    return models, None


async def _discover_groq(api_key: str) -> tuple[list[ModelSpecDTO], str | None]:
    if not api_key:
        return [], "Zapisz klucz API, żeby pobrać listę modeli Groq."

    async with httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT_SECONDS) as client:
        response = await client.get(
            "https://api.groq.com/openai/v1/models", headers={"Authorization": f"Bearer {api_key}"}
        )
        if response.status_code == 401:
            return [], "Klucz API odrzucony przez Groq."
        response.raise_for_status()
        payload = response.json()

    models = [
        ModelSpecDTO(id=entry["id"], label=entry["id"], options_schema=_groq_params_for(entry["id"]))
        for entry in payload.get("data", [])
        if entry.get("id")
    ]
    models.sort(key=lambda m: m.id.lower())
    return models, None


async def _discover_ollama(base_url: str) -> tuple[list[ModelSpecDTO], str | None]:
    """Lista to modele REALNIE pobrane na tej maszynie (`/api/tags`) — w odróżnieniu od
    chmury nie ma sensu pokazywać katalogu, którego użytkownik nie ma lokalnie."""
    async with httpx.AsyncClient(timeout=_DISCOVERY_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        payload = response.json()

    entries: list[dict[str, Any]] = payload.get("models", [])
    if not entries:
        return [], "Serwer Ollama nie ma pobranego żadnego modelu (`ollama pull ...`)."

    models = [
        ModelSpecDTO(
            id=entry.get("model") or entry["name"],
            label=entry.get("name") or entry["model"],
            options_schema=_ollama_params_for(
                entry.get("model") or entry.get("name", ""), (entry.get("details") or {}).get("family", "")
            ),
        )
        for entry in entries
        if entry.get("model") or entry.get("name")
    ]
    models.sort(key=lambda m: m.label.lower())
    return models, None
