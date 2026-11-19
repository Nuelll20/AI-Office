"""Buat PNG transparan dari aset uji menggunakan model lokal ComfyUI."""
import argparse
import hashlib
import html
import json
import re
import uuid
from urllib import error, request

from PIL import Image

from . import db
from .asset_proof import (
    digest,
    image_details,
    resume_image,
    write_json,
)
from .comfyui import ComfyUI
from .config import OUTPUT_DIR, env
from .story_worker import worker_lock


def background_models(nodes):
    spec = (
        nodes.get("LoadBackgroundRemovalModel", {})
        .get("input", {})
        .get("required", {})
        .get("bg_removal_name", [])
    )

    if spec and isinstance(spec[0], list):
        return spec[0]

    if len(spec) > 1 and spec[0] == "COMBO":
        return spec[1].get("options", [])

    return []


def choose_model(nodes):
    required = {
        "LoadImage": {"image"},
        "LoadBackgroundRemovalModel": {"bg_removal_name"},
        "RemoveBackground": {"image", "bg_removal_model"},
        "InvertMask": {"mask"},
        "JoinImageWithAlpha": {"image", "alpha"},
        "SaveImage": {"images", "filename_prefix"},
    }

    for name, fields in required.items():
        inputs = nodes.get(name, {}).get("input", {})
        available = (
            set(inputs.get("required", {}))
            | set(inputs.get("optional", {}))
        )

        if name not in nodes or not fields <= available:
            raise ValueError(
                f"Node/input ComfyUI belum sesuai: {name}"
            )

    models = background_models(nodes)

    if not models:
        raise ValueError(
            "Model background_removal belum tersedia. "
            "Pasang birefnet.safetensors dahulu."
        )

    selected = env("COMFYUI_BACKGROUND_MODEL")

    if selected and selected not in models:
        raise ValueError(
            "COMFYUI_BACKGROUND_MODEL tidak ditemukan "
            "di ComfyUI."
        )

    return selected or next(
        (
            name
            for name in models
            if "birefnet" in name.lower()
        ),
        models[0],
    )


def upload_png(client, source):
    image_details(source)

    data = source.read_bytes()
    filename = hashlib.sha256(data).hexdigest() + ".png"
    boundary = "AI_Office_" + uuid.uuid4().hex
    parts = []

    for name, value in (
        ("type", "input"),
        ("subfolder", "AI-Office/assets"),
        ("overwrite", "true"),
    ):
        parts.append(
            (
                f"--{boundary}\r\n"
                "Content-Disposition: form-data; "
                f'name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode()
        )

    parts.append(
        (
            f"--{boundary}\r\n"
            "Content-Disposition: form-data; "
            f'name="image"; filename="{filename}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
    )

    parts.extend((
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ))

    req = request.Request(
        client.url + "/upload/image",
        data=b"".join(parts),
        headers={
            "Content-Type": (
                "multipart/form-data; boundary=" + boundary
            )
        },
    )

    try:
        with request.urlopen(req, timeout=60) as response:
            result = json.load(response)
    except error.HTTPError as exc:
        raise RuntimeError(
            f"Upload PNG gagal: HTTP {exc.code}."
        ) from None
    except (error.URLError, OSError):
        raise RuntimeError(
            "Upload PNG gagal; periksa koneksi ComfyUI."
        ) from None

    if (
        result.get("type") != "input"
        or result.get("name") != filename
    ):
        raise ValueError(
            "Respons upload ComfyUI tidak sesuai "
            "nama/type berkas."
        )

    return "/".join(
        part
        for part in (
            result.get("subfolder", ""),
            filename,
        )
        if part
    )


def cutout_graph(image_name, model):
    def node(kind, **inputs):
        return {
            "class_type": kind,
            "inputs": inputs,
        }

    return {
        "1": node(
            "LoadImage",
            image=image_name,
        ),
        "2": node(
            "LoadBackgroundRemovalModel",
            bg_removal_name=model,
        ),
        "3": node(
            "RemoveBackground",
            image=["1", 0],
            bg_removal_model=["2", 0],
        ),
        "4": node(
            "InvertMask",
            mask=["3", 0],
        ),
        "5": node(
            "JoinImageWithAlpha",
            image=["1", 0],
            alpha=["4", 0],
        ),
        "7": node(
            "SaveImage",
            images=["5", 0],
            filename_prefix="AI-Office/cutout",
        ),
    }


def run_graph(client, graph, output):
    metadata = output.with_suffix(".render.json")

    if output.exists() and metadata.exists():
        saved = json.loads(
            metadata.read_text(encoding="utf-8")
        )

        if (
            saved.get("workflow") != graph
            or saved.get("server") != client.url
            or saved.get("image") != image_details(output)
        ):
            raise ValueError(
                f"Cache cutout tidak sesuai: {output}"
            )

        return

    job_file = output.with_suffix(".job.json")

    if not job_file.exists():
        if output.exists() or metadata.exists():
            raise ValueError(
                "Berkas cutout belum lengkap tanpa "
                f".job.json: {output}"
            )

        result = client.call(
            "/prompt",
            {
                "prompt": graph,
                "client_id": str(uuid.uuid4()),
            },
        )

        if (
            result.get("error")
            or result.get("node_errors")
            or not result.get("prompt_id")
        ):
            raise RuntimeError(
                f"Workflow cutout ditolak: {result}"
            )

        write_json(job_file, {
            "prompt_id": result["prompt_id"],
            "server": client.url,
            "workflow": graph,
        })

    details = resume_image(client, output, graph)

    write_json(metadata, {
        "server": client.url,
        "workflow": graph,
        "image": details,
    })


def alpha_details(path):
    with Image.open(path) as image:
        if "A" not in image.getbands():
            raise ValueError(
                f"Hasil tidak memiliki kanal alpha: {path}"
            )

        alpha = image.getchannel("A")
        low, high = alpha.getextrema()

        if low >= 32 or high <= 200:
            raise ValueError(
                "Mask transparansi belum valid: "
                f"alpha {low}..{high}"
            )

        bbox = alpha.point(
            lambda value: 255 if value > 16 else 0
        ).getbbox()

        if bbox is None:
            raise ValueError(
                f"Foreground kosong: {path}"
            )

        x0, y0, x1, y1 = bbox

        return {
            "bbox": list(bbox),
            "alpha_range": [low, high],
            "pivot_bottom": [
                (x0 + x1) / 2,
                y1,
            ],
            "pivot_center": [
                (x0 + x1) / 2,
                (y0 + y1) / 2,
            ],
        }


def latest_proof(video_id, video):
    root = OUTPUT_DIR / video_id / "asset-proof"
    candidates = []

    for path in root.glob("*/manifest.json"):
        try:
            value = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            continue

        if (
            value.get("complete") is True
            and value.get("purpose") == "style_proof"
            and value.get("video_id") == video_id
            and value.get("bible_revision")
            == video.get("bible_revision")
            and value.get("script_revision")
            == (video.get("script") or {}).get(
                "script_revision"
            )
        ):
            candidates.append((
                path.stat().st_mtime_ns,
                path,
                value,
            ))

    if not candidates:
        raise ValueError(
            "Belum ada uji aset lengkap yang sesuai "
            "revisi aktif."
        )

    _, path, value = max(
        candidates,
        key=lambda item: item[0],
    )

    return path.parent, value


def create_cutouts(video_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", video_id):
        raise ValueError("ID pekerjaan tidak valid.")

    video = db.get_video(video_id)

    if not video:
        raise ValueError("Pekerjaan tidak ditemukan.")

    source_folder, proof = latest_proof(video_id, video)

    client = ComfyUI()
    model = choose_model(client.call("/object_info"))

    folder = source_folder / (
        "cutouts-"
        + digest([
            model,
            client.url,
            "cutout-v1",
        ])[:16]
    )
    folder.mkdir(parents=True, exist_ok=True)

    records = []

    for asset in proof["assets"]:
        if asset["kind"] not in ("character", "prop"):
            continue

        source = (
            source_folder / asset["file"]
        ).resolve()

        if source.parent != source_folder.resolve():
            raise ValueError(
                "Path sumber keluar dari folder uji."
            )

        if image_details(source) != asset["image"]:
            raise ValueError(
                f"Gambar sumber berubah: {source}"
            )

        print(
            f"Membuat cutout: {asset['asset_id']}",
            flush=True,
        )

        uploaded = upload_png(client, source)
        graph = cutout_graph(uploaded, model)

        output = folder / (
            digest([asset["asset_id"], graph]) + ".png"
        )

        run_graph(client, graph, output)

        records.append({
            "asset_id": asset["asset_id"],
            "name": asset["name"],
            "kind": asset["kind"],
            "file": output.name,
            "image": image_details(output),
            **alpha_details(output),
        })

    if not records:
        raise ValueError(
            "Uji ini tidak memiliki tokoh/properti "
            "untuk dibuat transparan."
        )

    write_json(folder / "manifest.json", {
        "purpose": "cutout_proof",
        "video_id": video_id,
        "source_proof_id": proof["proof_id"],
        "model": model,
        "assets": records,
    })

    cards = "".join(
        "<article><h2>"
        + html.escape(item["name"])
        + '</h2><img src="'
        + html.escape(item["file"], quote=True)
        + '"></article>'
        for item in records
    )

    document = (
        '<!doctype html><html lang="id">'
        '<meta charset="utf-8">'
        "<title>Uji transparansi</title><style>"
        "body{font:16px system-ui;background:#f7eddc;"
        "padding:24px}"
        "main{display:flex;flex-wrap:wrap;gap:20px}"
        "article{width:300px}"
        "img{width:100%;background:"
        "repeating-conic-gradient("
        "#ddd 0 25%,#fff 0 50%) 0/20px 20px}"
        "</style><h1>Uji transparansi aset</h1>"
        "<p>Pola kotak menunjukkan area transparan. "
        "Periksa tepi objek dan bagian tubuh yang "
        "mungkin terpotong.</p><main>"
        + cards
        + "</main></html>"
    )

    path = folder / "index.html"
    path.write_text(document, encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if not args.id and not args.check:
        parser.error("Gunakan --id ID atau --check.")

    try:
        if args.check:
            nodes = ComfyUI().call("/object_info")
            print(json.dumps({
                "background_models": background_models(nodes),
            }, indent=2))
        else:
            with worker_lock(
                "asset-cutout.lock",
                "Bayu cutout",
            ):
                result = create_cutouts(args.id)

            print(f"PRATINJAU CUTOUT: {result}")

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