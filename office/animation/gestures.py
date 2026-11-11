"""Gestur percakapan yang mengikuti waktu dialog dan dapat dipakai ulang."""

import math

GESTURES = frozenset((
    "none",
    "ask",
    "explain",
    "point",
))


def sample_gesture(line, index, fps):
    """Tentukan jenis, kekuatan, dan kemajuan gestur."""

    if line is None:
        return "none", 0.0, 0.0

    kind = line.get("gesture", "explain")

    if not isinstance(kind, str) or kind not in GESTURES:
        raise ValueError("Jenis gestur tidak dikenal.")

    start = line["start_frame"]
    end = line["end_frame"]

    if kind == "none" or not start <= index < end:
        return "none", 0.0, 0.0

    elapsed = (index - start) / fps
    duration = (end - start) / fps

    # Tangan bergerak masuk dan kembali secara bertahap.
    attack = min(0.25, duration / 4)
    release = min(0.35, duration / 4)

    weight = min(
        1.0,
        elapsed / attack,
        (duration - elapsed) / release,
    )

    weight = weight * weight * (3 - 2 * weight)

    return kind, weight, elapsed / duration


def gesture_angles(kind, phase):
    """Sudut lengan atas dan lengan bawah untuk setiap gestur."""

    if kind == "ask":
        return (
            35 + 4 * math.sin(math.pi * phase),
            105,
        )

    if kind == "explain":
        beat = math.sin(4 * math.pi * phase)

        return (
            35 + 7 * beat,
            88 + 10 * beat,
        )

    if kind == "point":
        return 60, 95

    if kind == "none":
        return 0, 0

    raise ValueError("Jenis gestur tidak dikenal.")