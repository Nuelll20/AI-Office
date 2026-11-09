import json
import time
import urllib.request

from .config import DATA_DIR, env

OFFSET_FILE = DATA_DIR / "tg_offset.txt"


def configured():
    return bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))


def _call(method, payload, timeout=30):
    url = f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/{method}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def send(text):
    """Kirim pesan ke Telegram. Return True kalau sukses (tidak pernah raise)."""
    if not configured():
        return False
    try:
        _call("sendMessage", {"chat_id": env("TELEGRAM_CHAT_ID"), "text": text})
        return True
    except Exception as e:
        print(f"(Telegram gagal: {e})")
        return False


def _offset():
    try:
        return int(OFFSET_FILE.read_text())
    except Exception:
        return 0


def wait_reply(timeout_sec=600):
    """Tunggu 1 pesan teks dari chat bos. Return teks atau None."""
    end = time.time() + timeout_sec
    chat = str(env("TELEGRAM_CHAT_ID"))
    while time.time() < end:
        try:
            wait = int(max(1, min(20, end - time.time())))
            res = _call("getUpdates", {"offset": _offset(), "timeout": wait}, timeout=wait + 10)
        except Exception as e:
            print(f"(getUpdates gagal: {e})")
            time.sleep(3)
            continue
        for u in res.get("result", []):
            OFFSET_FILE.write_text(str(u["update_id"] + 1))
            m = u.get("message") or {}
            if str(m.get("chat", {}).get("id")) == chat and m.get("text"):
                return m["text"]
    return None
