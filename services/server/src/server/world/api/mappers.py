"""Mappery: byty domenowe Świata -> DTO warstwy REST.

Wspólne dla wszystkich routerów w `world/api/`, bo ten sam byt bywa potrzebny
w kilku miejscach (pokój pojawia się w odpowiedzi o urządzenia i o klientów).
Zero logiki domenowej — wyłącznie przepisanie pól i maskowanie sekretu.
"""

from __future__ import annotations

from shared import is_secret_ref

from server.ai.provider_crud import mask_secret_value
from server.world.dto import (
    ConditionSpecDTO,
    DeclaredDeviceDTO,
    HomeAssistantConfigDTO,
    PlaceholderSpecDTO,
    PromptSectionDTO,
    PromptSectionsResponse,
    RoomDTO,
    SenderProfileDTO,
)
from server.world.models import DeclaredDeviceEntry, Device, HomeAssistantConfig, RoomInstanceConfig, SenderProfile
from server.world.prompt_sections import CONDITION_SPECS, PLACEHOLDER_SPECS, PromptSectionsConfig, section_warnings


def mask_token(token: str) -> str:
    """Maskuje token dostępu do ostatnich 4 widocznych znaków.

    Ta sama maska co dla kluczy API dostawców AI (`ai/provider_crud.py`) — token
    Home Assistant to jedyny sekret poza nimi, który opuszcza serwer w postaci
    podglądowej, więc nie ma powodu, żeby wyglądał inaczej. Referencja `env:NAZWA`
    przechodzi bez maski z tego samego powodu co tam: to nazwa zmiennej, nie sekret."""
    if not token or is_secret_ref(token):
        return token
    return mask_secret_value(token)


def to_config_dto(cfg: HomeAssistantConfig) -> HomeAssistantConfigDTO:
    return HomeAssistantConfigDTO(base_url=cfg.base_url, access_token=mask_token(cfg.access_token))


def to_room_dto(cfg: RoomInstanceConfig) -> RoomDTO:
    return RoomDTO(id=cfg.id, name=cfg.name)


def to_declared_dto(
    entity_id: str, entry: DeclaredDeviceEntry, resolved: Device | None, rooms_by_id: dict[str, RoomInstanceConfig]
) -> DeclaredDeviceDTO:
    room = rooms_by_id.get(entry.room_id) if entry.room_id else None
    return DeclaredDeviceDTO(
        entity_id=entity_id,
        display_name=entry.display_name,
        effective_name=resolved.name if resolved is not None else (entry.display_name or entity_id),
        kind=resolved.kind if resolved is not None else "",
        capabilities=sorted(resolved.capabilities.keys()) if resolved is not None else [],
        room_id=entry.room_id,
        room_name=room.name if room is not None else None,
    )


def to_sections_response(config: PromptSectionsConfig) -> PromptSectionsResponse:
    """Sekcje w kolejności zapisu (= kolejność w prompcie) wraz z metadanymi
    warunków i podstawień, żeby UI nie duplikowało etykiet."""
    return PromptSectionsResponse(
        sections=[
            PromptSectionDTO(
                id=section.id,
                label=section.label,
                text=section.text,
                text_negated=section.text_negated,
                condition=section.condition,
                condition_param=section.condition_param,
                warnings=section_warnings(section),
            )
            for section in config.sections
        ],
        conditions=[
            ConditionSpecDTO(key=spec.key, label=spec.label, param_source=spec.param_source)
            for spec in CONDITION_SPECS
        ],
        placeholders=[
            PlaceholderSpecDTO(token=spec.token, label=spec.label, guaranteed_by=list(spec.guaranteed_by))
            for spec in PLACEHOLDER_SPECS
        ],
    )


def to_sender_dto(sender_id: str, profile: SenderProfile, rooms_by_id: dict[str, RoomInstanceConfig]) -> SenderProfileDTO:
    room = rooms_by_id.get(profile.room_id) if profile.room_id else None
    return SenderProfileDTO(
        sender_id=sender_id,
        display_name=profile.display_name,
        room_id=profile.room_id,
        room_name=room.name if room is not None else None,
        # Posortowane — `frozenset` nie ma kolejności, a UI renderuje to wprost;
        # bez sortowania kolejność potrafiłaby się zmieniać między odpowiedziami.
        capabilities=sorted(profile.capabilities),
    )
