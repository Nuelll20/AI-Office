"""Uji gaya aset dari storyboard; belum merupakan aset animasi final."""

import argparse
import hashlib
import html
import json
import re
import time
from urllib import parse
from PIL import Image
from .asset_prompts import prepare_asset
from . import db
from .comfyui import ComfyUI, workflow
from .config import OUTPUT_DIR, env
from .story_worker import worker_lock
from pathlib import Path


def digest(value):
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def select_samples(board):
    source = board.get("assets")

    if isinstance(source, dict):
        assets = [dict(value, id=key) for key, value in source.items()]
    elif isinstance(source, list):
        assets = source
    else:
        raise ValueError("Storyboard tidak memiliki daftar assets yang valid.")

    selected = []

    for kind in ("character", "location", "prop"):
        candidates = [asset for asset in assets if asset.get("kind") == kind]

        # Mulai dari identitas dasar, bukan varian yang
        # membutuhkan gambar referensi sebelumnya.
        if kind == "character":
            candidates = [
                asset for asset in candidates if not asset.get("reference_asset_id")
            ]

        if candidates:
            selected.append(candidates[0])

    if not selected:
        raise ValueError(
            "Tidak ditemukan aset tokoh, lokasi, atau " "properti untuk diuji."
        )

    return selected


STYLE_PREFIX = (
    "Simple full-color 2.5D clay cartoon, "
    "rounded matte shapes, soft shading. "
)
NEGATIVE_PROMPT = (
    "photograph, photorealistic, product photography, "
    "realistic skin, anime, manga, black and white, "
    "monochrome, grayscale, line art, sketch, ink drawing, "
    "heavy outlines, character sheet, model sheet, "
    "reference sheet, turnaround, multiple views, "
    "collage, split screen, duplicate subject, "
    "text, watermark, logo, blurry, low quality, "
    "distorted anatomy"
)


def sample_prompt(asset):
    subject = asset.get("render_subject")

    if not isinstance(subject, str) or not subject.strip():
        raise ValueError(
            "Spesifikasi gambar belum disiapkan: "
            f"{asset['id']}"
        )

    presentation = {
        "character": (
            "One isolated full-body character, centered, "
            "single view, plain white background."
        ),
        "location": (
            "Empty animation background, clear floor space, "
            "neutral lighting."
        ),
        "prop": (
            "One isolated object, entirely visible, "
            "three-quarter view, plain white background."
        ),
    }

    return (
        subject.strip().rstrip(".")
        + ". "
        + STYLE_PREFIX
        + presentation[asset["kind"]]
    )


def sample_negative(asset):
    parts = (
        NEGATIVE_PROMPT.split(",")
        + asset["forbidden_features"]
    )

    if asset["kind"] == "character":
        parts.extend([
            "extra characters",
            "scenery",
            "display base",
            "ground patch",
        ])
    elif asset["kind"] == "prop":
        parts.extend([
            "characters",
            "scenery",
            "display base",
        ])
    else:
        parts.append("characters")

    seen = set()
    result = []

    for part in parts:
        value = part.strip()

        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())

    return ", ".join(result)

def image_details(path):
    path = Path(path)

    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError(
                f"Berkas bukan PNG: {path}"
            )

        image.verify()

    with Image.open(path) as image:
        image.load()
        dimensions = list(image.size)

    return {
        "sha256": hashlib.sha256(
            path.read_bytes()
        ).hexdigest(),
        "size": dimensions,
    }

def resume_image(client, output, expected_workflow):
    job_file = output.with_suffix(".job.json")
    job = json.loads(job_file.read_text(encoding="utf-8"))

    if (
        job.get("server", "").rstrip("/") != client.url.rstrip("/")
        or job.get("workflow") != expected_workflow
    ):
        raise ValueError(f"Identitas server/workflow job berbeda: {job_file}")

    prompt_id = job.get("prompt_id")

    if not isinstance(prompt_id, str) or not prompt_id:
        raise ValueError(f"prompt_id tidak valid: {job_file}")

    timeout = float(env("COMFYUI_TIMEOUT", "600"))

    if not 0 < timeout <= 86400:
        raise ValueError("COMFYUI_TIMEOUT harus lebih dari 0, " "maksimal 86400 detik.")

    deadline = time.monotonic() + timeout
    missing = 0
    last_state = None

    print(
        f"Memulihkan job lama: {prompt_id}",
        flush=True,
    )

    while time.monotonic() < deadline:
        request_timeout = max(
            0.1,
            min(30, deadline - time.monotonic()),
        )

        history = client.call(
            "/history/" + parse.quote(prompt_id, safe=""),
            timeout=request_timeout,
        )

        result = history.get(prompt_id, {})
        status = result.get("status", {})

        if status.get("status_str") == "error":
            messages = json.dumps(
                status.get("messages", []),
                ensure_ascii=False,
            )
            raise RuntimeError(f"Job lama {prompt_id} gagal: " f"{messages[:2000]}")

        if status.get("completed"):
            images = result.get("outputs", {}).get("7", {}).get("images", [])

            if not images:
                raise RuntimeError(
                    f"Job {prompt_id} selesai tanpa " "gambar pada node 7."
                )

            image = images[0]
            query = parse.urlencode(
                {
                    "filename": image["filename"],
                    "subfolder": image.get("subfolder", ""),
                    "type": image.get("type", "output"),
                }
            )

            data = client.call(
                "/view?" + query,
                raw=True,
                timeout=request_timeout,
            )

            if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Hasil pemulihan bukan PNG.")

            temporary = output.with_suffix(".resume.png")

            try:
                temporary.write_bytes(data)
                details = image_details(temporary)

                if output.exists():
                    if output.read_bytes() != data:
                        raise RuntimeError(
                            "PNG lokal berbeda dengan " f"hasil job: {output}"
                        )
                else:
                    temporary.replace(output)
            finally:
                temporary.unlink(missing_ok=True)

            return details

        queue = client.call(
            "/queue",
            timeout=request_timeout,
        )

        state = next(
            (
                label
                for key, label in (
                    ("queue_running", "sedang dirender"),
                    ("queue_pending", "menunggu antrean"),
                )
                if any(
                    isinstance(entry, (list, tuple))
                    and len(entry) > 1
                    and entry[1] == prompt_id
                    for entry in queue.get(key, [])
                )
            ),
            None,
        )

        if state is None:
            missing += 1

            # Job mungkin sedang berpindah dari antrean
            # ke riwayat saat kedua endpoint diperiksa.
            if missing >= 3:
                raise RuntimeError(
                    f"Job {prompt_id} tidak ditemukan "
                    "di antrean/riwayat. Riwayat mungkin "
                    "sudah dibersihkan atau server "
                    "dimulai ulang. Job tidak dikirim "
                    "ulang otomatis."
                )
        else:
            missing = 0

            if state != last_state:
                print(
                    f"Job lama {state}.",
                    flush=True,
                )
                last_state = state

        time.sleep(
            min(
                2,
                max(0, deadline - time.monotonic()),
            )
        )

    raise TimeoutError(
        f"Job {prompt_id} belum selesai. "
        "Jalankan kembali perintah yang sama "
        "untuk melanjutkan."
    )


def write_preview(folder, board, records):
    cards = []

    for record in records:
        cards.append(
            "<article><h2>"
            + html.escape(record["name"])
            + "</h2><p>"
            + html.escape(record["asset_id"])
            + '</p><img src="'
            + html.escape(record["file"], quote=True)
            + '" alt="Uji aset"></article>'
        )

    title = html.escape(str(board.get("title", "Uji aset")))

    document = (
        '<!doctype html><html lang="id">'
        '<meta charset="utf-8">'
        '<meta name="viewport" '
        'content="width=device-width,initial-scale=1">'
        "<title>Uji aset</title><style>"
        "body{font:16px system-ui;background:#f7eddc;"
        "color:#40332d;margin:24px}"
        "main{display:flex;flex-wrap:wrap;gap:20px}"
        "article{background:white;padding:16px;"
        "border-radius:12px;width:300px}"
        "h2{font-size:18px}"
        "p{overflow-wrap:anywhere}"
        "img{width:100%;height:auto}</style>"
        "<h1>" + title + "</h1><p>Uji gaya gambar. Latar putih belum "
        "transparan; aset belum dilengkapi rig atau "
        "variasi pose.</p><main>" + "".join(cards) + "</main></html>"
    )

    temporary = folder / "index.html.tmp"
    temporary.write_text(document, encoding="utf-8")
    temporary.replace(folder / "index.html")


def generate_proof(video_id, seed=42):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
        raise ValueError("ID pekerjaan tidak valid.")

    if not 0 <= seed < 2**64:
        raise ValueError(
            "Seed harus antara 0 dan 2**64 - 1."
        )

    video = db.get_video(video_id)

    if not video:
        raise ValueError(
            f"Pekerjaan {video_id} tidak ditemukan."
        )

    board = video.get("scenes")

    if (
        not isinstance(board, dict)
        or board.get("schema_version") != 3
    ):
        raise ValueError(
            "Pekerjaan belum memiliki storyboard Bayu versi 3."
        )

    if video.get("status") != "storyboard_ready":
        raise ValueError(
            "Uji ini membutuhkan status storyboard_ready."
        )

    script = video.get("script") or {}

    if (
        board.get("bible_revision")
        != video.get("bible_revision")
        or board.get("script_revision")
        != script.get("script_revision")
    ):
        raise ValueError(
            "Storyboard tidak sesuai dengan "
            "revisi cerita/naskah aktif."
        )

    client = ComfyUI()
    checkpoint = env("COMFYUI_CHECKPOINT")

    if (
        not checkpoint
        or checkpoint not in client.checkpoints()
    ):
        raise ValueError(
            "Checkpoint tidak tersedia. Jalankan "
            "python -m office.comfyui check."
        )

    # Inisialisasi sebelum perulangan penyusunan aset.
    plan = []

    for original in select_samples(board):
        print(
            f"Menyiapkan spesifikasi aset: {original['id']}",
            flush=True,
        )

        asset = prepare_asset(
            video_id,
            video,
            original,
        )

        prompt = sample_prompt(asset)
        negative = sample_negative(asset)

        asset_seed = int(
            digest([video_id, asset["id"], seed])[:16],
            16,
        )

        plan.append({
            "asset": asset,
            "prompt": prompt,
            "negative_prompt": negative,
            "seed": asset_seed,
            "workflow": workflow(
                checkpoint,
                prompt,
                asset_seed,
                negative_prompt=negative,
            ),
        })

    proof_id = digest({
        "board": board,
        "plan": plan,
        "server": client.url,
    })

    folder = (
        OUTPUT_DIR
        / video_id
        / "asset-proof"
        / proof_id
    )
    folder.mkdir(parents=True, exist_ok=True)

    records = []

    for item in plan:
        asset = item["asset"]

        name = (
            asset["kind"]
            + "-"
            + digest(asset["id"])[:16]
        )

        output = folder / (name + ".png")
        metadata = folder / (name + ".proof.json")
        job_file = output.with_suffix(".job.json")

        saved = None

        if metadata.exists():
            saved = json.loads(
                metadata.read_text(encoding="utf-8")
            )

            if (
                saved.get("proof_id") != proof_id
                or saved.get("asset_id") != asset["id"]
                or saved.get("workflow") != item["workflow"]
            ):
                raise RuntimeError(
                    "Metadata tidak sesuai rencana aset: "
                    f"{metadata}"
                )

        if output.exists() and saved is not None:
            details = image_details(output)

            if saved.get("image") != details:
                raise RuntimeError(
                    f"Cache berubah atau rusak: {output}"
                )

            print(
                f"Pakai hasil tersimpan: {asset['id']}",
                flush=True,
            )

        elif job_file.exists():
            details = resume_image(
                client,
                output,
                item["workflow"],
            )

            if (
                saved is not None
                and saved.get("image") != details
            ):
                raise RuntimeError(
                    "Hasil pemulihan berbeda dari "
                    f"metadata: {output}"
                )

            print(
                f"Hasil job lama dipulihkan: {asset['id']}",
                flush=True,
            )

        elif output.exists() or metadata.exists():
            raise RuntimeError(
                "Berkas belum lengkap dan tidak "
                f"memiliki .job.json: {output}"
            )

        else:
            print(
                f"Membuat {asset['kind']}: {asset['id']}",
                flush=True,
            )

            client.generate(
                item["prompt"],
                output,
                seed=item["seed"],
                negative_prompt=item["negative_prompt"],
            )

            details = image_details(output)

        write_json(metadata, {
            "proof_id": proof_id,
            "asset_id": asset["id"],
            "seed": item["seed"],
            "workflow": item["workflow"],
            "image": details,
        })

        records.append({
            "asset_id": asset["id"],
            "name": asset.get("name", asset["id"]),
            "kind": asset["kind"],
            "file": output.name,
            "image": details,
        })

        write_json(folder / "manifest.json", {
            "video_id": video_id,
            "proof_id": proof_id,
            "purpose": "style_proof",
            "bible_revision": board["bible_revision"],
            "script_revision": board["script_revision"],
            "complete": len(records) == len(plan),
            "assets": records,
        })

        write_preview(folder, board, records)

    return folder / "index.html"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    try:
        with worker_lock(
            "asset-proof.lock",
            "Bayu uji aset",
        ):
            result = generate_proof(
                args.id,
                args.seed,
            )

        print(f"PRATINJAU: {result}")

    except (
        RuntimeError,
        ValueError,
        KeyError,
        OSError,
        TypeError,
    ) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()
