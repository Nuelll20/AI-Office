"""Pengolah suara dialog yang dapat digunakan untuk berbagai cerita."""

import array
import math
import subprocess
import sys

from .scene_audio import RATE


def prepare_dialogue(pcm, *, shift=0, max_pause=None):
    """
    Mengolah suara sebelum dimasukkan ke dalam video.

    pcm:
        Data suara yang akan diolah.

    shift:
        Perubahan tinggi nada.
        Nilai negatif membuat suara lebih rendah.
        Nilai positif membuat suara lebih tinggi.
        Nilai 0 mempertahankan tinggi nada semula.

    max_pause:
        Batas jeda panjang di tengah ucapan, dalam detik.
        Jika None, jeda di tengah ucapan dipertahankan.
    """

    if not pcm or len(pcm) % 2:
        raise ValueError(
            "Data suara kosong atau tidak lengkap."
        )

    if (
        type(shift) not in (int, float)
        or not math.isfinite(shift)
        or not -4 <= shift <= 4
    ):
        raise ValueError(
            "Nilai shift harus berada di antara -4 dan +4."
        )

    if max_pause is not None and (
        type(max_pause) not in (int, float)
        or not math.isfinite(max_pause)
        or not 0.15 <= max_pause <= 1
    ):
        raise ValueError(
            "Nilai max_pause harus berada di antara "
            "0.15 dan 1 detik."
        )

    original_sec = len(pcm) / (2 * RATE)

    # Ubah tinggi nada jika diminta.
    if shift:
        shifted_rate = round(
            RATE * 2 ** (shift / 12)
        )
        ratio = shifted_rate / RATE

        filters = (
            f"asetrate={shifted_rate},"
            f"aresample={RATE},"
            f"atempo={1 / ratio:.10f}"
        )

        result = subprocess.run(
            [
                "ffmpeg",
                "-v", "error",
                "-f", "s16le",
                "-ar", str(RATE),
                "-ac", "1",
                "-i", "pipe:0",
                "-af", filters,
                "-f", "s16le",
                "-ar", str(RATE),
                "-ac", "1",
                "pipe:1",
            ],
            input=pcm,
            capture_output=True,
            timeout=120,
        )

        if result.returncode:
            detail = result.stderr.decode(
                errors="replace"
            )[-500:]

            raise ValueError(
                "FFmpeg gagal mengolah suara: " + detail
            )

        pcm = result.stdout

        if not pcm or len(pcm) % 2:
            raise ValueError(
                "FFmpeg menghasilkan suara kosong "
                "atau tidak lengkap."
            )

    samples = array.array("h")
    samples.frombytes(pcm)

    if sys.byteorder != "little":
        samples.byteswap()

    # Periksa kekuatan suara setiap 10 milidetik.
    window = RATE // 100
    threshold = 32768 * 10 ** (-48 / 20)
    active = []

    for start in range(0, len(samples), window):
        chunk = samples[start:start + window]

        rms = math.sqrt(
            sum(value * value for value in chunk)
            / len(chunk)
        )

        if rms >= threshold:
            active.append(start // window)

    if not active:
        raise ValueError(
            "Tidak ditemukan suara yang cukup kuat. "
            "Periksa suara sumber."
        )

    # Sisakan sedikit ruang agar awal dan akhir kata tetap terdengar.
    left = max(
            0,
            active[0] * window - round(0.06 * RATE),
    )

    right = min(
            len(samples),
            (active[-1] + 1) * window
            + round(0.10 * RATE),
    )

    output = array.array("h")
    cursor = left
    removed = 0

    # Batasi jeda panjang di tengah ucapan jika diminta.
    if max_pause is not None:
        keep = round(max_pause * RATE)

        for before, after in zip(
            active, active[1:]
        ):
            begin = (before + 1) * window
            end = after * window

            minimum = round(
                max(0.7, max_pause + 0.1) * RATE
            )

            # Jeda pendek tetap dipertahankan.
            if end - begin < minimum:
                continue

            cut_start = begin + keep // 2
            cut_end = end - (keep - keep // 2)

            output.extend(
                samples[cursor:cut_start]
            )

            cursor = cut_end
            removed += cut_end - cut_start

    output.extend(samples[cursor:right])

    if sys.byteorder != "little":
        output.byteswap()

    processed = output.tobytes()

    # Catat hasil pengolahan untuk pemeriksaan.
    return processed, {
        "input_sec": round(original_sec, 4),
        "output_sec": round(
            len(processed) / (2 * RATE), 4
        ),
        "trimmed_edges_sec": round(
            (left + len(samples) - right) / RATE,
            4,
        ),
        "shortened_pauses_sec": round(
            removed / RATE, 4
        ),
        "shift_semitones": shift,
    }