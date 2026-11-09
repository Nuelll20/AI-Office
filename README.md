# Kantor AI - Fase 1

Alur: Scout (Adit) -> Telegram -> Creative Director (Agus) -> Writer (Rina)
-> Visual Director (Bayu) -> Editor/QC (Sari, placeholder) -> folder output + notifikasi.

Perintah (jalankan dari folder ini):

    python3 -m office.cli scout            # Adit cari 6 ide, kirim ke Telegram / cetak
    python3 -m office.cli pick 1 3 5       # pilih manual (atau tanpa angka = tunggu balasan Telegram)
    python3 -m office.cli idea "teks ide"  # masukkan ide sendiri langsung ke antrean
    python3 -m office.cli produce          # produksi 1 video (--all untuk semua antrean)
    python3 -m office.cli status
    python3 -m office.cli ui               # tampilan kantor di http://localhost:8000
    python3 -m office.cli demo             # 1 video contoh (mercusuar)

Hasil per video ada di output/<id>/: style_pack.json, script.json, scenes.json, upload_info.txt
Daftar gaya/suara/musik bisa diedit di config/pools.json tanpa mengubah kode.

## Produksi Fase 2

Perintah `python -m office.cli produce --id ID_VIDEO` menjalankan
persiapan naskah, gambar, narasi, render klip, dan penggabungan final.

Hasil akhir tersimpan di `output/ID_VIDEO/final.mp4`.

- Hasil media yang masih cocok digunakan kembali.
- Pekerjaan gagal atau dihentikan dapat dilanjutkan dengan ID yang sama.
- `produce` tanpa ID mengambil satu pekerjaan berstatus queued.
- `produce --all` memproses seluruh pekerjaan berstatus queued.
- LLM_MODE=mock hanya menyimulasikan pembuatan teks.
- Pembuatan gambar menggunakan ComfyUI.
- Pembuatan suara menggunakan edge-tts dan memerlukan internet.
- Render dan penggabungan menggunakan FFmpeg.
