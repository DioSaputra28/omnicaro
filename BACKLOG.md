# Backlog omnicaro

Ide/pekerjaan yang ditunda, bukan bug aktif.

## Akun download terpisah untuk scrape (belum dikerjakan)

**Diminta:** pemisahan eksplisit antara akun untuk membuka halaman Carousell MY /
mengunduh foto dan akun untuk upload.

**Kondisi sekarang:**
- Scrape berjalan anonim (`requests` tanpa cookie) — halaman MY publik.
- Cookie akun di Manajemen Akun hanya dipakai untuk upload ke `id.carousell.com`.
- Tidak ada field peran akun (`download` / `upload` / `keduanya`) dan tidak ada
  pilihan akun download di form scrape.

**Rencana bila dikerjakan:**
- Tambah `role` di tabel `accounts` + UI Manajemen Akun.
- Form scrape dapat pilihan "Akun download (opsional)"; kosong = tetap anonim.
- Opsional: rotasi proxy khusus scrape.

**Alasan ditunda:** khawatir memicu verifikasi CAPTCHA / proteksi Cloudflare di
Carousell MY bila scrape memakai sesi login. Selama scrape anonim masih lancar,
biarkan apa adanya.

**Pemicu untuk dikerjakan:** scrape mulai diblokir/rate-limited dari IP lokal,
atau butuh konten yang hanya tampil untuk user login.
