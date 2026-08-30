"""Testy lokalnej bramki energii ograniczającej pracę serwerowego wake-worda."""

from desktop_satellite.wake_gate import WakeAudioGate


def _frame(amplitude: int) -> bytes:
    return amplitude.to_bytes(2, "little", signed=True) * 2


def test_quiet_frames_are_buffered_but_not_emitted() -> None:
    gate = WakeAudioGate(20.0, amplitude_threshold=500, preroll_ms=60.0)

    assert gate.process(_frame(100)).frames == ()
    assert gate.process(_frame(200)).frames == ()


def test_first_loud_frame_opens_stream_and_flushes_preroll() -> None:
    gate = WakeAudioGate(20.0, amplitude_threshold=500, preroll_ms=60.0)
    quiet_a = _frame(100)
    quiet_b = _frame(200)
    loud = _frame(700)
    gate.process(quiet_a)
    gate.process(quiet_b)

    emission = gate.process(loud)

    assert emission.starts_stream is True
    assert emission.frames == (quiet_a, quiet_b, loud)


def test_gate_closes_after_hangover_and_next_sound_starts_new_stream() -> None:
    gate = WakeAudioGate(20.0, amplitude_threshold=500, preroll_ms=20.0, hangover_ms=40.0)
    loud = _frame(700)
    quiet = _frame(100)
    gate.process(loud)

    assert gate.process(quiet).frames == (quiet,)
    assert gate.process(quiet).frames == (quiet,)
    assert gate.process(quiet).frames == ()
    assert gate.process(loud).starts_stream is True


def test_reset_discards_open_stream_and_buffer() -> None:
    gate = WakeAudioGate(20.0, amplitude_threshold=500, preroll_ms=40.0)
    gate.process(_frame(700))

    gate.reset()

    assert gate.process(_frame(100)).frames == ()
