"""Reproduce Aurora's original, soft water-bubble confirmation (no samples)."""
from array import array
import math
from pathlib import Path
import random
import sys
import wave


def make_feedback(destination: Path) -> None:
    rate, duration = 44100, 0.32
    rng = random.Random(603)
    samples = []
    phase = 0.0
    body_phase = 0.0
    for index in range(round(rate * duration)):
        t = index / rate
        # Rising resonance mimics a water bubble shrinking as it surfaces.
        frequency = 430 + 640 * (1 - math.exp(-t / 0.052))
        phase += 2 * math.pi * frequency / rate
        body_phase += 2 * math.pi * (240 + 110 * math.exp(-t / 0.04)) / rate
        attack = 1 - math.exp(-t / 0.005)
        decay = math.exp(-t / 0.052)
        rounded = (math.sin(phase) + 0.16 * math.sin(phase * 1.97)) * attack * decay
        body = 0.30 * math.sin(body_phase) * (1 - math.exp(-t / 0.012)) * math.exp(-t / 0.065)
        # A faint air component supplies water texture without a mechanical click.
        air = 0.024 * rng.uniform(-1, 1) * attack * math.exp(-t / 0.012)
        tail = min(1.0, max(0.0, (duration - t) / 0.025)) ** 2
        samples.append((rounded + body + air) * tail)
    peak = max(abs(sample) for sample in samples)
    pcm = array("h", (round(sample / peak * 0.59 * 32767) for sample in samples))
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm.tobytes())


if __name__ == "__main__":
    make_feedback(Path(__file__).resolve().parents[1] / "assets" / "command_click.wav")
