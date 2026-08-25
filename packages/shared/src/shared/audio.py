"""Analiza sygnału PCM16 — współdzielona przez lokalny VAD/wake-word satelity
i serwera oraz przez serwerową bramkę przed STT (ten sam próg amplitudy
używany po obu stronach, patrz `docs/manifest.md` sekcja 3.6)."""

import struct


def peak_amplitude(pcm_chunk: bytes) -> int:
    """Szczytowa amplituda próbek PCM16 mono w danej porcji (0 dla pustej/nieparzystej porcji)."""
    sample_count = len(pcm_chunk) // 2
    if sample_count == 0:
        return 0
    samples = struct.unpack(f"<{sample_count}h", pcm_chunk[: sample_count * 2])
    return max(abs(s) for s in samples)
