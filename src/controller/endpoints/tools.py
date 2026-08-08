import json
from fastapi import APIRouter
from fastapi.responses import Response

from protocol.schemas import ToolExecutionRequest
import controller.core.app_state as app_state

router_tools = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
#  Proxy Narzędzi (Tool Execution)
# ─────────────────────────────────────────────────────────────────────────────

@router_tools.post("/v1/tools/execute")
async def execute_tool_proxy(request: ToolExecutionRequest):
    """Proxy wywołań narzędzi. Usługi klienta wywołują ten endpoint.

    Kontroler jest jedynym źródłem prawdy dla Home Assistant (MANIFEST.md §3.1).
    Parametr `room` z requesta jest przekazywany do ToolsRegistry — filtruje urządzenia
    do pokoju Satelity, która zainicjowała żądanie.
    Zwraca wynik jako string JSON (identyczny format co ToolsRegistry.execute_tool).
    """
    if not app_state.tools_registry:
        return Response(
            json.dumps({"error": "Rejestr narzędzi niedostępny."}, ensure_ascii=False),
            status_code=503,
            media_type="application/json"
        )
    # Wstrzykujemy room do argumentów — execute_tool odczyta go przez dispatch
    arguments = dict(request.arguments)
    if request.room is not None and "room" not in arguments:
        arguments["room"] = request.room
    result = app_state.tools_registry.execute_tool(request.tool_name, arguments)
    return Response(content=result, media_type="application/json")

@router_tools.get("/v1/tools/menu")
async def get_global_menu():
    """Zwraca globalne menu w postaci Markdown."""
    if not app_state.tools_registry:
        return Response(content="BRAK REJESTRU", status_code=503)
    return Response(content=app_state.tools_registry.get_global_menu(), media_type="text/plain")
