"""Koneksi ComfyUI dan uji gambar untuk checkpoint SDXL standar."""
import argparse
import json
import time
import uuid
from pathlib import Path
from urllib import error, parse, request

from .config import OUTPUT_DIR, env


class ComfyUI:
    def __init__(self):
        self.url = env(
            "COMFYUI_URL", "http://127.0.0.1:8188"
        ).rstrip("/")

    def call(self, path, payload=None, raw=False, timeout=30):
        body = (
            None
            if payload is None
            else json.dumps(payload).encode("utf-8")
        )
        req = request.Request(
            self.url + path,
            data=body,
            headers={"Content-Type": "application/json"},
        )

        try:
            with request.urlopen(req, timeout=timeout) as response:
                result = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode(
                "utf-8", errors="replace"
            )[:2000]
            raise RuntimeError(
                f"ComfyUI HTTP {exc.code}: {detail}"
            ) from exc
        except (error.URLError, OSError) as exc:
            raise RuntimeError(
                f"Tidak bisa mengakses {self.url}: {exc}"
            ) from exc

        return result if raw else json.loads(result)

    def checkpoints(self):
        data = self.call("/object_info/CheckpointLoaderSimple")
        return data["CheckpointLoaderSimple"]["input"][
            "required"
        ]["ckpt_name"][0]

    def generate(self, prompt, output, seed=42):
        if not prompt.strip():
            raise ValueError("Prompt tidak boleh kosong.")

        if not 0 <= seed < 2**64:
            raise ValueError(
                "Seed harus antara 0 dan 2**64 - 1."
            )

        checkpoint = env("COMFYUI_CHECKPOINT")
        if not checkpoint or checkpoint not in self.checkpoints():
            raise ValueError(
                "COMFYUI_CHECKPOINT belum cocok. "
                "Jalankan perintah check."
            )

        timeout = float(env("COMFYUI_TIMEOUT", "600"))
        if not 0 < timeout <= 86400:
            raise ValueError(
                "COMFYUI_TIMEOUT harus lebih dari 0, "
                "maksimal 86400 detik."
            )

        output = Path(output).resolve()
        if output.suffix.lower() != ".png":
            raise ValueError(
                "Output harus menggunakan ekstensi .png."
            )

        output.parent.mkdir(parents=True, exist_ok=True)
        graph = workflow(checkpoint, prompt, seed)

        result = self.call(
            "/prompt",
            {
                "prompt": graph,
                "client_id": str(uuid.uuid4()),
            },
        )

        if result.get("error") or result.get("node_errors"):
            raise RuntimeError(f"Workflow ditolak: {result}")

        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(
                f"Respons tidak memiliki prompt_id: {result}"
            )

        # Simpan identitas pekerjaan untuk pemeriksaan jika gagal.
        output.with_suffix(".job.json").write_text(
            json.dumps(
                {
                    "prompt_id": prompt_id,
                    "server": self.url,
                    "workflow": graph,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"Job terkirim: {prompt_id}", flush=True)
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            history = self.call(
                "/history/" + parse.quote(prompt_id, safe=""),
                timeout=max(0.1, min(30, remaining)),
            )

            job = history.get(prompt_id, {})
            status = job.get("status", {})

            if status.get("status_str") == "error":
                raise RuntimeError(
                    f"Render gagal: {status.get('messages', [])}"
                )

            if status.get("completed"):
                images = (
                    job.get("outputs", {})
                    .get("7", {})
                    .get("images", [])
                )

                if not images:
                    raise RuntimeError(
                        "Job selesai, tetapi node SaveImage "
                        "tidak menghasilkan gambar."
                    )

                image = images[0]
                query = parse.urlencode(
                    {
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    }
                )

                data = self.call("/view?" + query, raw=True)

                if (
                    len(data) < 33
                    or not data.startswith(b"\x89PNG\r\n\x1a\n")
                ):
                    raise RuntimeError(
                        "Hasil unduhan bukan berkas PNG "
                        "yang diharapkan."
                    )

                # Tulis sementara, lalu pindahkan setelah lengkap.
                temporary = output.with_suffix(".png.part")
                temporary.write_bytes(data)
                temporary.replace(output)
                return output

            time.sleep(
                min(2, max(0, deadline - time.monotonic()))
            )

        raise TimeoutError(
            f"Batas tunggu habis. Job {prompt_id} mungkin "
            "masih berjalan. Periksa antrean ComfyUI "
            "sebelum mengirim ulang."
        )


def workflow(checkpoint, prompt, seed):
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}

    return {
        "1": node(
            "CheckpointLoaderSimple",
            ckpt_name=checkpoint,
        ),
        "2": node(
            "CLIPTextEncode",
            clip=["1", 1],
            text=prompt,
        ),
        "3": node(
            "CLIPTextEncode",
            clip=["1", 1],
            text=(
                "text, watermark, logo, blurry, "
                "low quality, distorted anatomy"
            ),
        ),
        "4": node(
            "EmptyLatentImage",
            width=576,
            height=1024,
            batch_size=1,
        ),
        "5": node(
            "KSampler",
            model=["1", 0],
            positive=["2", 0],
            negative=["3", 0],
            latent_image=["4", 0],
            seed=seed,
            steps=20,
            cfg=7.0,
            sampler_name="dpmpp_2m",
            scheduler="karras",
            denoise=1.0,
        ),
        "6": node(
            "VAEDecode",
            samples=["5", 0],
            vae=["1", 2],
        ),
        "7": node(
            "SaveImage",
            images=["6", 0],
            filename_prefix="AI-Office/test",
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(
        dest="command", required=True
    )
    commands.add_parser("check")

    generate = commands.add_parser("generate")
    generate.add_argument("--prompt", required=True)
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "smoke-test" / "image.png",
    )

    args = parser.parse_args()
    client = ComfyUI()

    try:
        if args.command == "check":
            client.call("/system_stats")
            print(f"ComfyUI terhubung: {client.url}")

            models = client.checkpoints()
            print("Checkpoint yang tersedia:")
            for name in models:
                print(f"  - {name}")

            if not models:
                print("  (belum ada checkpoint)")

            selected = env("COMFYUI_CHECKPOINT")
            print(
                f"Checkpoint terpilih: "
                f"{selected or '(belum diisi)'}"
            )
            print(
                f"Nama ditemukan: "
                f"{'YA' if selected in models else 'TIDAK'}"
            )
        else:
            path = client.generate(
                args.prompt, args.output, args.seed
            )
            print(f"Gambar tersimpan: {path}")

    except (RuntimeError, ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"GAGAL: {exc}\n")


if __name__ == "__main__":
    main()