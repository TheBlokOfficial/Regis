"""Gateway — jedyny agregator Warstwy 0 (kernel) łączący Pluginy i Dostawców
kontekstu w trzy płaskie kanały treści agenta (wizja, sekcja 2 i 3).

Budowany od zera przy każdej turze agenta (nigdy cache'owany), w jednym
przebiegu — pyta każdy zarejestrowany Plugin i każdego Dostawcę kontekstu
o jego wkład, skleja w trzy płaskie listy, rozstrzyga kolizje nazw
narzędzi i nadaje encjom opaque identyfikatory. Nie interpretuje treści
niczego, co dostaje — rozmawia wyłącznie z Pluginami, nigdy bezpośrednio
z żadną integracją wewnątrz nich.
"""

import hashlib
from dataclasses import dataclass
from typing import Any

from shared import get_logger

from server.agent.backend import ToolDefinition, ToolResult
from server.agent.context_provider_contract import ContextProvider, Fact
from server.agent.plugin_contract import EntitySpec, PluginProvider, ToolDispatch

logger = get_logger("regis.agent.gateway")

_OPAQUE_ID_LENGTH = 16


def _compute_opaque_id(plugin_id: str, native_ref: str) -> str:
    """Wylicza deterministyczny, nieprzezroczysty identyfikator encji.

    Zależy wyłącznie od (tożsamość pluginu + wewnętrzne odniesienie nadane
    przez ten plugin) — bez żadnej pamiętanej między turami tabeli, ta sama
    para zawsze da ten sam skrót (wizja, sekcja 4.2). Skrót kryptograficzny
    (nie czytelna konkatenacja) celowo nie zdradza pochodzenia encji.
    """
    digest = hashlib.sha256(f"{plugin_id}\x00{native_ref}".encode("utf-8")).hexdigest()
    return digest[:_OPAQUE_ID_LENGTH]


@dataclass
class GatewayBuild:
    """Kompletny wkład Gateway na czas jednej interakcji agenta."""

    tool_definitions: list[ToolDefinition]
    entities: list[EntitySpec]
    facts: list[Fact]
    dispatch: ToolDispatch


class Gateway:
    """Agregator Warstwy 0 — jedyny punkt zbierający wkład Pluginów i
    Dostawców kontekstu (wizja, sekcja 2)."""

    def __init__(
        self,
        plugins: list[PluginProvider] | None = None,
        context_providers: list[ContextProvider] | None = None,
    ) -> None:
        self.plugins: list[PluginProvider] = plugins or []
        self.context_providers: list[ContextProvider] = context_providers or []

    async def build(self) -> GatewayBuild:
        """Buduje pełny kontekst agenta na czas jednej interakcji, od zera.

        Polityka kolizji nazw narzędzi: jeśli dwa pluginy zarejestrują
        narzędzie o tej samej nazwie, wcześniej zarejestrowany wygrywa —
        kolidujące narzędzie późniejszego pluginu jest logowane jako błąd
        i pomijane (bez cichego nadpisania) — tak jak dziś na poziomie kernela.
        """
        facts: list[Fact] = []
        for provider in self.context_providers:
            facts.extend(await provider.get_facts())

        all_tool_defs: list[ToolDefinition] = []
        tool_owner: dict[str, PluginProvider] = {}
        plugin_dispatch: dict[int, ToolDispatch] = {}
        routing_table: dict[str, tuple[PluginProvider, str]] = {}
        agent_entities: list[EntitySpec] = []

        for plugin in self.plugins:
            contribution = await plugin.build(facts)

            for tool_def in contribution.tools:
                if tool_def.name in tool_owner:
                    logger.error(
                        f"Konflikt nazw narzędzi: '{tool_def.name}' jest już zarejestrowane przez inny plugin "
                        f"— pomijam duplikat z pluginu [{plugin.plugin_id}]."
                    )
                    continue
                tool_owner[tool_def.name] = plugin
                all_tool_defs.append(tool_def)

            plugin_dispatch[id(plugin)] = contribution.dispatch

            for entity in contribution.entities:
                native_ref = entity.id
                opaque_id = _compute_opaque_id(plugin.plugin_id, native_ref)
                routing_table[opaque_id] = (plugin, native_ref)
                agent_entities.append(EntitySpec(id=opaque_id, name=entity.name, capabilities=entity.capabilities))

        async def combined_dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            plugin = tool_owner.get(name)
            if plugin is None:
                return ToolResult(is_error=True, content=f"Nieznane narzędzie: '{name}'.")

            call_arguments = arguments
            if "entity_id" in arguments:
                opaque_id = str(arguments["entity_id"])
                routed = routing_table.get(opaque_id)
                if routed is None:
                    return ToolResult(
                        is_error=True,
                        content=(
                            f"Nieznana lub nieaktualna encja '{opaque_id}'. "
                            "Sprawdź aktualną listę dostępnych encji w kontekście."
                        ),
                    )
                routed_plugin, native_ref = routed
                if routed_plugin is not plugin:
                    return ToolResult(
                        is_error=True,
                        content=f"Encja '{opaque_id}' nie należy do pluginu obsługującego narzędzie '{name}'.",
                    )
                call_arguments = {**arguments, "entity_id": native_ref}

            dispatch = plugin_dispatch[id(plugin)]
            return await dispatch(name, call_arguments)

        return GatewayBuild(
            tool_definitions=all_tool_defs,
            entities=agent_entities,
            facts=facts,
            dispatch=combined_dispatch,
        )
