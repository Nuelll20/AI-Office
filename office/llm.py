import json
import re

from .config import env

_announced = False


def is_mock():
    mode = env("LLM_MODE", "auto")
    if mode == "mock":
        return True
    if mode == "real":
        return False
    return not env("ANTHROPIC_API_KEY")


def _extract_json(text):
    text = re.sub(r"```(?:json)?", "", text).strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        raise ValueError("Tidak ada JSON di respons model")
    s = min(starts)
    e = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[s:e + 1])


def ask_json(system, user, mock, max_tokens=3000):
    """Panggil LLM dan kembalikan JSON. mock = fungsi pengganti saat mode mock."""
    global _announced
    if is_mock():
        if not _announced:
            print("MODE MOCK: LLM tidak dipanggil (isi ANTHROPIC_API_KEY di .env untuk mode asli)")
            _announced = True
        return mock()

    import anthropic
    client = anthropic.Anthropic()
    sys_prompt = system + "\n\nBalas HANYA dengan JSON valid tanpa teks lain."
    last_err = None
    for _ in range(2):
        msg = client.messages.create(
            model=env("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            max_tokens=max_tokens,
            system=sys_prompt,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        try:
            return _extract_json(text)
        except Exception as e:  # coba sekali lagi
            last_err = e
    raise RuntimeError(f"Gagal parse JSON dari model: {last_err}")
