"""Testy `SilenceVadDetector` — czyste dane PCM, bez sprzętu."""

from desktop_satellite.vad import SilenceVadDetector

FRAME_DURATION_MS = 20.0


def _loud_frame() -> bytes:
    return (30000).to_bytes(2, byteorder="little", signed=True) * 160


def _quiet_frame() -> bytes:
    return (10).to_bytes(2, byteorder="little", signed=True) * 160


def test_silence_from_the_start_triggers_after_threshold() -> None:
    """Użytkownik nic nie mówi po wake-wordzie (fałszywe wykrycie/wahanie) — VAD musi
    mimo to wyzwolić po pełnym progu ciszy, żeby satelita nie wisiała w nieskończoność
    w RECORDING_UTTERANCE czekając na mowę, która nigdy nie nadejdzie."""
    vad = SilenceVadDetector(frame_duration_ms=FRAME_DURATION_MS, silence_duration_ms=100.0)
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is True


def test_silence_after_speech_triggers_after_threshold() -> None:
    vad = SilenceVadDetector(frame_duration_ms=FRAME_DURATION_MS, silence_duration_ms=100.0)
    assert vad.process(_loud_frame()) is False
    # próg 100ms / 20ms na ramkę = 5 ramek ciszy wymaganych
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is True


def test_loud_frame_resets_silence_counter() -> None:
    vad = SilenceVadDetector(frame_duration_ms=FRAME_DURATION_MS, silence_duration_ms=100.0)
    vad.process(_loud_frame())
    for _ in range(4):
        vad.process(_quiet_frame())
    assert vad.process(_loud_frame()) is False
    for _ in range(4):
        assert vad.process(_quiet_frame()) is False
    assert vad.process(_quiet_frame()) is True


def test_reset_clears_state() -> None:
    vad = SilenceVadDetector(frame_duration_ms=FRAME_DURATION_MS, silence_duration_ms=40.0)
    vad.process(_loud_frame())
    vad.process(_quiet_frame())
    vad.reset()
    assert vad.process(_quiet_frame()) is False
