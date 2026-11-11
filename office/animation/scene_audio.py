"""PCM per kalimat, cache isi, dan amplitudo mulut berbasis frame."""
import array
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

RATE = 24000


def run(command):
    result = subprocess.run(
        command,
        capture_output=True,
        timeout=180,
    )
    if result.returncode:
        raise ValueError(
            f"{Path(command[0]).name} gagal: "
            f"kode {result.returncode}."
        )


def read_pcm(path):
    with wave.open(str(path), "rb") as source:
        settings = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
        )

        if settings != (1, 2, RATE):
            raise ValueError(
                "Audio harus PCM mono 16-bit 24000 Hz."
            )

        pcm = source.readframes(source.getnframes())

    if not pcm:
        raise ValueError("Audio kosong.")

    return pcm


def write_pcm(path, pcm):
    with wave.open(str(path), "wb") as target:
        target.setparams(
            (1, 2, RATE, 0, "NONE", "not compressed")
        )
        target.writeframes(pcm)


def speech(text, voice, folder, tone=False):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    key = hashlib.sha256(
        json.dumps(
            {
                "text": text,
                "voice": voice,
                "tone": tone,
                "version": 1,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()

    path = folder / (key + ".wav")
    meta = path.with_suffix(".json")

    try:
        saved = json.loads(meta.read_text(encoding="utf-8"))

        if saved["sha256"] == hashlib.sha256(
            path.read_bytes()
        ).hexdigest():
            return read_pcm(path)

    except (
        OSError, ValueError, KeyError,
        wave.Error, EOFError,
    ):
        pass

    with tempfile.TemporaryDirectory(dir=folder) as temporary:
        wav = Path(temporary) / "line.wav"

        if tone:
            samples = array.array("h")
            frequency = 190 + int(voice["pitch"][:-2]) / 2
            count = round(max(0.5, len(text) * 0.045) * RATE)

            for index in range(count):
                t = index / RATE
                envelope = max(0, math.sin(2 * math.pi * 4 * t))

                samples.append(
                    round(
                        7000 * envelope
                        * math.sin(2 * math.pi * frequency * t)
                    )
                )

            if sys.byteorder != "little":
                samples.byteswap()

            write_pcm(wav, samples.tobytes())

        else:
            executable = Path(sys.executable).with_name(
                "edge-tts.exe"
                if os.name == "nt"
                else "edge-tts"
            )

            if not executable.exists():
                raise ValueError(
                    "edge-tts belum tersedia pada environment ini."
                )

            mp3 = Path(temporary) / "line.mp3"

            run([
                str(executable),
                "--voice", voice["id"],
                "--rate=" + voice["rate"],
                "--pitch=" + voice["pitch"],
                "--text=" + text,
                "--write-media", str(mp3),
            ])

            run([
                "ffmpeg", "-y", "-v", "error",
                "-i", str(mp3),
                "-ar", str(RATE),
                "-ac", "1",
                "-c:a", "pcm_s16le",
                str(wav),
            ])

        pcm = read_pcm(wav)
        wav.replace(path)

        info = Path(temporary) / "meta.json"
        info.write_text(
            json.dumps({
                "sha256": hashlib.sha256(
                    path.read_bytes()
                ).hexdigest(),
            })
        )
        info.replace(meta)

    return pcm


def mouth_levels(pcm, samples_per_frame):
    samples = array.array("h")
    samples.frombytes(pcm)

    if sys.byteorder != "little":
        samples.byteswap()

    result = []

    for start in range(0, len(samples), samples_per_frame):
        chunk = samples[start:start + samples_per_frame]
        rms = math.sqrt(
            sum(value * value for value in chunk) / len(chunk)
        )
        result.append(
            min(1.0, max(0.0, (rms - 180) / 2200))
        )

    return result