"""Volume-adjusted WAV feedback without importing QtMultimedia or changing system volume."""
from __future__ import annotations

from array import array
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from .core import application_db_path


def adjusted_sound(source: Path, volume: int, cache_dir: Path | None = None) -> Path:
    volume = max(0, min(100, int(volume)))
    if volume == 100:
        return Path(source)
    target_dir = Path(cache_dir) if cache_dir is not None else application_db_path().parent / "audio-cache"
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / f"aurora-glub-{volume}.wav"
    # Regenerate on update, but avoid disk work on every expansion.
    if destination.is_file() and destination.stat().st_mtime_ns >= Path(source).stat().st_mtime_ns:
        return destination
    with wave.open(str(source), "rb") as reader:
        channels, width, rate = reader.getnchannels(), reader.getsampwidth(), reader.getframerate()
        if channels != 1 or width != 2:
            raise ValueError("Formato de áudio inesperado: esperado WAV PCM mono de 16 bits.")
        raw = reader.readframes(reader.getnframes())
    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    gain = volume / 100.0
    for index, sample in enumerate(samples):
        samples[index] = round(sample * gain)
    if sys.byteorder != "little":
        samples.byteswap()
    temp = destination.with_suffix(".tmp")
    try:
        with wave.open(str(temp), "wb") as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(width)
            writer.setframerate(rate)
            writer.writeframes(samples.tobytes())
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)
    return destination


def play_feedback(source: Path, *, enabled: bool, volume: int) -> None:
    if not enabled or volume <= 0:
        return
    sound = adjusted_sound(source, volume)
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(str(sound), winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return
    for player in ("paplay", "pw-play", "aplay"):
        binary = shutil.which(player)
        if binary:
            subprocess.Popen([binary, str(sound)], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return
