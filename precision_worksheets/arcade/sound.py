"""Little synthesized sound effects for the Word Arcade.

The sounds are generated as tiny WAV files the first time they're needed
(so there are no audio files to ship or license) and played with Qt's
QSoundEffect. Everything here is optional: if Qt Multimedia isn't
available, or there's no audio device, `play` silently does nothing and
the games work exactly the same without sound.
"""

from __future__ import annotations

import math
import os
import struct
import tempfile
import wave

_RATE = 22050
_enabled = True
_effects: dict = {}
_failed = False

# name -> list of (frequency Hz, duration s) notes, plus a waveform.
_SOUNDS = {
    "good": ([(660, 0.07), (990, 0.12)], "square"),
    "bad": ([(220, 0.09), (165, 0.16)], "square"),
    "pop": ([(900, 0.03), (1400, 0.05)], "sine"),
    "click": ([(700, 0.04)], "sine"),
    "tick": ([(520, 0.1)], "sine"),
    "go": ([(784, 0.08), (1046, 0.2)], "square"),
    "star": ([(1046, 0.06), (1318, 0.06), (1568, 0.12)], "sine"),
    "win": ([(523, 0.1), (659, 0.1), (784, 0.1), (1046, 0.28)], "square"),
    "whoosh": ([(300, 0.05), (450, 0.05), (650, 0.05), (900, 0.08)], "sine"),
    "flip": ([(480, 0.04)], "sine"),
}


def set_enabled(on: bool) -> None:
    global _enabled
    _enabled = on


def is_enabled() -> bool:
    return _enabled


def _synth(notes, wave_kind: str) -> bytes:
    frames = bytearray()
    for freq, dur in notes:
        n = int(_RATE * dur)
        for i in range(n):
            t = i / _RATE
            env = min(1.0, i / (0.005 * _RATE)) * (1 - i / n) ** 1.5
            ph = math.sin(2 * math.pi * freq * t)
            v = (1.0 if ph >= 0 else -1.0) * 0.35 if wave_kind == "square" else ph * 0.6
            frames += struct.pack("<h", int(v * env * 12000))
    return bytes(frames)


def _path_for(name: str) -> str:
    folder = os.path.join(tempfile.gettempdir(), "precision_worksheets_sounds")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}.wav")
    if not os.path.exists(path):
        notes, kind = _SOUNDS[name]
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(_RATE)
            w.writeframes(_synth(notes, kind))
    return path


def play(name: str) -> None:
    global _failed
    if not _enabled or _failed or name not in _SOUNDS:
        return
    try:
        effect = _effects.get(name)
        if effect is None:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect

            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(_path_for(name)))
            effect.setVolume(0.45)
            _effects[name] = effect
        effect.play()
    except Exception:  # no multimedia module / audio device - just stay quiet
        _failed = True
