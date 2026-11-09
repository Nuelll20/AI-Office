# Versi Python dari setup_ai_office.sh (untuk Windows tanpa bash).
# Jalankan dari folder tujuan:  python setup_ai_office.py
# Membaca setup_ai_office.sh di folder yang sama dan membuat semua file di folder ini.
import re, sys
from pathlib import Path

src = Path(__file__).with_name("setup_ai_office.sh")
if not src.exists():
    sys.exit("setup_ai_office.sh harus ada di folder yang sama dengan file ini.")

target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
for d in ["office", "config", "ui", "data", "output"]:
    (target / d).mkdir(parents=True, exist_ok=True)

lines = src.read_text(encoding="utf-8").splitlines()
i, count = 0, 0
pat = re.compile(r"""^cat > (\S+) <<'(\w+)'\s*$""")
while i < len(lines):
    m = pat.match(lines[i])
    if not m:
        i += 1
        continue
    path, tag = m.group(1), m.group(2)
    i += 1
    body = []
    while i < len(lines) and lines[i] != tag:
        body.append(lines[i])
        i += 1
    i += 1
    out = target / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(body) + "\n", encoding="utf-8")
    count += 1
    print("dibuat:", out)

print(f"\nSelesai. {count} file dibuat di {target.resolve()}")
print("Lanjut:  python -m office.cli demo")
