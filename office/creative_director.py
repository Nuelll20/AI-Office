"""Agus - Creative Director: memilih style pack yang dikunci per video.
Murni kode + random (bukan LLM) supaya aturan anti-monoton pasti ditegakkan."""
import copy
import random

from . import db
from .config import load_json

KEYS = ["genre", "structure", "visual_style", "palette", "narrator", "music"]


def _signature(pack):
    return {k: pack[k]["id"] for k in KEYS}


def _diff(a, b):
    sa, sb = a["signature"], b.get("signature", {})
    return sum(1 for k in KEYS if sa[k] != sb.get(k))


def _random_pack(pools, rng):
    pack = {
        "genre": rng.choice(pools["genres"]),
        "structure": rng.choice(pools["structures"]),
        "visual_style": rng.choice(pools["visual_styles"]),
        "palette": rng.choice(pools["palettes"]),
        "narrator": rng.choice(pools["narrators"]),
        "music": rng.choice(pools["music"]),
        "subtitle": rng.choice(pools["subtitles"]),
        "pacing": rng.choice(pools["pacing"]),
        "duration_sec": rng.randrange(pools["duration_range"][0], pools["duration_range"][1] + 1, 5),
        "brand": pools["brand"],
    }
    pack = copy.deepcopy(pack)
    pack["signature"] = _signature(pack)
    return pack


def make_style_pack(idea, rng=random):
    pools = load_json("pools.json")
    history = db.recent_style_packs(pools["history_size"])
    need = pools["min_elements_different"]

    best = None
    for _ in range(500):
        cand = _random_pack(pools, rng)
        worst = min((_diff(cand, h) for h in history), default=len(KEYS))
        if best is None or worst > best[0]:
            best = (worst, cand)
        if worst >= need:
            break
    worst, pack = best
    pack.update({
        "idea": idea,
        "locked": True,
        "diff_vs_history": {
            "checked_last": len(history),
            "min_elements_different": worst,
            "passed": worst >= need,
        },
    })
    return pack
