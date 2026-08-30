"""Kodek ramek protokołu głosowego (`shared/voice_frames.py`).

Najważniejszy test w tym pliku to **złoty wzorzec drutu**: bajt w bajt te same ramki
JSON, jakie obie usługi wysyłały przed wprowadzeniem kodeka. To jedyne, co gwarantuje,
że stara satelita i nowy serwer (oraz odwrotnie) pozostają zgodne — a satelitę
aktualizuje się ręcznie, na innej maszynie, więc rozjazd wersji jest tu normalnym
stanem, nie wyjątkiem.
"""

from __future__ import annotations

import json

from shared import (
    ClientConfigFrame,
    ErrorFrame,
    HelloFrame,
    PlaybackDoneFrame,
    SatelliteMessageType,
    ServerMessageType,
    TurnEndFrame,
    UtteranceEndFrame,
    WakeStreamStartFrame,
    decode_satellite_frame,
    decode_server_frame,
    encode_frame,
    satellite_control_frame,
    server_control_frame,
)

# Postać na drucie sprzed kodeka — dokładnie to, co produkowały `json.dumps`
# w `voice/gateway.py` i `desktop_satellite/protocol_client.py`.
WIRE_FORMAT = {
    "hello": ({"type": "hello", "capabilities": ["mic", "speaker"]}, HelloFrame(capabilities=["mic", "speaker"])),
    "wake_stream_start": ({"type": "wake_stream_start"}, WakeStreamStartFrame()),
    "utterance_end": ({"type": "utterance_end"}, UtteranceEndFrame()),
    "playback_done": ({"type": "playback_done"}, PlaybackDoneFrame()),
    "wake_detected": ({"type": "wake_detected"}, server_control_frame(ServerMessageType.WAKE_DETECTED)),
    "play_stop_tone": ({"type": "play_stop_tone"}, server_control_frame(ServerMessageType.PLAY_STOP_TONE)),
    "tts_start": ({"type": "tts_start"}, server_control_frame(ServerMessageType.TTS_START)),
    "tts_end": ({"type": "tts_end"}, server_control_frame(ServerMessageType.TTS_END)),
    "turn_end": ({"type": "turn_end"}, TurnEndFrame()),
    "error": ({"type": "error", "detail": "coś poszło nie tak"}, ErrorFrame(detail="coś poszło nie tak")),
    "client_config": (
        {"type": "client_config", "silence_duration_ms": 1500.0, "amplitude_threshold": 500},
        ClientConfigFrame(silence_duration_ms=1500.0, amplitude_threshold=500),
    ),
}


def test_wire_format_is_unchanged() -> None:
    """Każda ramka koduje się do dokładnie tego samego JSON-a co przed kodekiem."""
    for name, (expected, frame) in WIRE_FORMAT.items():
        assert json.loads(encode_frame(frame)) == expected, name


def test_round_trip_in_both_directions() -> None:
    for name, (wire, frame) in WIRE_FORMAT.items():
        decode = (
            decode_satellite_frame
            if wire["type"] in ("hello", "wake_stream_start", "utterance_end", "playback_done")
            else decode_server_frame
        )
        assert decode(json.dumps(wire)) == frame, name


def test_payload_is_typed_not_dug_out_of_a_dict() -> None:
    """Powód istnienia kodeka: `frame["silence_duration_ms"]` na surowym dicie ujawniał
    literówkę dopiero jako `KeyError` w runtime u klienta."""
    frame = decode_server_frame('{"type": "client_config", "silence_duration_ms": 900, "amplitude_threshold": 300}')

    assert isinstance(frame, ClientConfigFrame)
    assert frame.silence_duration_ms == 900.0
    assert frame.amplitude_threshold == 300


def test_unknown_type_is_none_not_an_exception() -> None:
    """Nowszy serwer może mówić więcej, niż starsza satelita zna. Nierozpoznana ramka
    ma być zignorowana, nie ma zrywać połączenia."""
    assert decode_server_frame('{"type": "cos_z_przyszlosci"}') is None
    assert decode_satellite_frame('{"type": "cos_z_przyszlosci"}') is None


def test_malformed_input_is_none() -> None:
    assert decode_server_frame("to nie jest JSON") is None
    # Brak wymaganych pól payloadu też jest odrzuceniem — połowicznie zdekodowana
    # ramka konfiguracji byłaby gorsza niż jej brak (cichy zły próg VAD).
    assert decode_server_frame('{"type": "client_config"}') is None


def test_direction_is_asymmetric_on_purpose() -> None:
    """Serwer dekoduje wyłącznie ramki satelity i odwrotnie — ramka z niewłaściwego
    kierunku jest dla dekodera nieznana."""
    assert decode_satellite_frame('{"type": "wake_detected"}') is None
    assert decode_server_frame('{"type": "hello", "capabilities": []}') is None


def test_control_frame_helpers_reject_types_carrying_payload() -> None:
    """`ERROR` i `CLIENT_CONFIG` trzeba zbudować jawnie — zbudowanie ich „po typie"
    pominęłoby pola, co byłoby cichym błędem."""
    for message_type in (ServerMessageType.ERROR, ServerMessageType.CLIENT_CONFIG):
        try:
            server_control_frame(message_type)
        except KeyError:
            continue
        raise AssertionError(f"{message_type} nie powinien dać się zbudować bez payloadu")

    try:
        satellite_control_frame(SatelliteMessageType.HELLO)
    except KeyError:
        return
    raise AssertionError("HELLO nie powinien dać się zbudować bez capabilities")
