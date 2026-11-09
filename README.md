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
