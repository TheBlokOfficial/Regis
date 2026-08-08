"""
Schematy narzędzi dla domeny agent/prompt/.

Re-eksportuje BASE_TOOLS_SCHEMA i get_tools_schema z tools/schemas.py
(jedynego źródła definicji) — zachowuje zgodność z importami.
"""
from controller.agent.tools.schemas import BASE_TOOLS_SCHEMA, get_tools_schema

__all__ = ["BASE_TOOLS_SCHEMA", "get_tools_schema"]
