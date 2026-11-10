"""Klien JSON AI Office melalui API OpenAI-compatible milik 9router."""
import json
import math
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .config import env

_announced = False


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def is_mock():
    mode = env("LLM_MODE", "auto").strip().lower()

    if mode not in {"auto", "mock", "real"}:
        raise RuntimeError("LLM_MODE harus auto, mock, atau real.")

    if mode == "mock":
        return True

    if mode == "real":
        return False

    return not any(
        env(name).strip()
        for name in (
            "ROUTER_BASE_URL",
            "ROUTER_API_KEY",
            "ROUTER_MODEL",
        )
    )


def settings():
    base = env("ROUTER_BASE_URL").strip().rstrip("/")
    key = env("ROUTER_API_KEY").strip()
    model = env("ROUTER_MODEL").strip()

    if not all((base, key, model)):
        raise RuntimeError(
            "Lengkapi ROUTER_BASE_URL, ROUTER_API_KEY, "
            "dan ROUTER_MODEL di .env."
        )

    url = urlsplit(base)

    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or not url.path.endswith("/v1")
    ):
        raise RuntimeError(
            "ROUTER_BASE_URL harus alamat API yang berakhir /v1."
        )

    try:
        timeout = float(env("ROUTER_TIMEOUT", "180"))

        if not math.isfinite(timeout) or not 1 <= timeout <= 600:
            raise ValueError

    except ValueError:
        raise RuntimeError(
            "ROUTER_TIMEOUT harus 1 sampai 600 detik."
        ) from None

    return base, key, model, timeout


def _extract_json(text):
    text = text.strip()

    fence = re.fullmatch(
        r"```(?:json)?\s*\n?(.*?)\n?```",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if fence:
        text = fence.group(1).strip()

    result = json.loads(text)

    if not isinstance(result, (dict, list)):
        raise ValueError("Respons harus objek atau array JSON.")

    return result


def _request(messages, max_tokens):
    base, key, model, timeout = settings()

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
    }

    request = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(
            payload,
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        opener = urllib.request.build_opener(NoRedirect())

        with opener.open(request, timeout=timeout) as response:
            data = json.load(response)

    except urllib.error.HTTPError as exc:
        hints = {
            400: "Periksa kompatibilitas model dan parameter permintaan.",
            401: "Periksa API key 9router.",
            403: "Periksa izin API key dan akses model.",
            404: "Periksa base URL dan ID model/combo.",
            429: "Periksa kuota atau batas permintaan di 9router.",
        }

        hint = hints.get(
            exc.code,
            "Periksa status dan log server 9router.",
        )

        raise RuntimeError(
            f"9router HTTP {exc.code}. {hint}"
        ) from None

    except (TimeoutError, urllib.error.URLError):
        raise RuntimeError(
            "9router tidak terjangkau atau melewati batas waktu."
        ) from None

    except (ValueError, UnicodeError):
        raise RuntimeError(
            "Respons HTTP 9router bukan JSON yang valid."
        ) from None

    if not isinstance(data, dict) or data.get("error"):
        raise RuntimeError(
            "9router mengembalikan respons gagal."
        )

    choices = data.get("choices")

    if (
        not isinstance(choices, list)
        or not choices
        or not isinstance(choices[0], dict)
    ):
        raise RuntimeError(
            "Respons 9router tidak memiliki choices yang valid."
        )

    choice = choices[0]
    reason = choice.get("finish_reason")

    if reason == "length":
        raise RuntimeError(
            "Respons terpotong. Naikkan max_tokens "
            "atau ringkas permintaan."
        )

    if reason not in (None, "stop"):
        raise RuntimeError(
            "Model tidak menyelesaikan respons teks secara normal."
        )

    message = choice.get("message")
    content = (
        message.get("content")
        if isinstance(message, dict)
        else None
    )

    if isinstance(content, list):
        content = "".join(
            part["text"]
            for part in content
            if isinstance(part, dict)
            and part.get("type") == "text"
            and isinstance(part.get("text"), str)
        )

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            "Model tidak mengembalikan isi teks."
        )

    return content


def ask_json(system, user, mock, max_tokens=3000):
    global _announced

    if is_mock():
        if not _announced:
            print("MODE MOCK: tidak memanggil API AI.")
            _announced = True

        return mock()

    if not isinstance(max_tokens, int) or max_tokens < 1:
        raise ValueError(
            "max_tokens harus bilangan bulat positif."
        )

    messages = [
        {
            "role": "system",
            "content": system + (
                "\nBalas HANYA dengan objek atau array JSON valid. "
                "Tanpa Markdown, komentar, atau penjelasan di luar JSON."
            ),
        },
        {
            "role": "user",
            "content": user,
        },
    ]

    for attempt in range(2):
        text = _request(messages, max_tokens)

        try:
            return _extract_json(text)

        except ValueError:
            if attempt == 0:
                print(
                    "Format JSON belum valid; mencoba sekali lagi..."
                )

                messages[1]["content"] = user + (
                    "\nPastikan jawaban berupa JSON lengkap "
                    "yang dapat diparsing."
                )

    raise RuntimeError(
        "Model belum menghasilkan JSON valid setelah dua percobaan."
    )