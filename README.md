# omnicaro

Otomasi jual-beli barang second di Carousell: scrape katalog (MY) → posting ke akun (ID), lewat **web dashboard**.

Cross-platform (Windows/Linux/macOS), tanpa ketergantungan API Windows. Akun ditambahkan dengan **menempel cookie Carousell** hasil ekstrak dari browser, lalu divalidasi otomatis.

## Jalankan

```bash
pip install -r requirements.txt
python run.py
```

Buka `http://127.0.0.1:8080`.

Panduan lengkap deploy ke VPS (systemd, Nginx, HTTPS, backup, troubleshooting):
**[DEPLOY_VPS.md](./DEPLOY_VPS.md)**.

## Menambah akun (cookie)

1. Login Carousell di browser (mis. Brave/Chrome).
2. Ekstrak cookie domain `carousell.com` (mis. extension "Cookie-Editor" → Export JSON, atau DevTools → Application → Cookies).
3. Dashboard → tab **Akun** → tempel JSON → **Tambah akun**.
4. omnicaro memvalidasi login dengan membuka `id.carousell.com` memakai cookie tersebut.

Cookie disimpan di `omnicaro/data/omnicaro.db` (SQLite). Jangan bagikan file DB ini.

## Fitur

- Scrape kategori MY (HTTP + foto penuh, dedup URL & SHA-256).
- Upload per akun memakai `storage_state` (cookie), tanpa profil browser.
- **Rotasi User Agent**: 200 UA master (Chrome/Edge/Firefox/Safari/Opera/Vivaldi
  desktop, versi stabil per Okt 2026) bisa dicari, ditambah, dinonaktifkan, atau
  dihapus. Saat posting UA dipilih bergiliran (LRU) — mode per akun, per listing,
  atau mati. Tiap UA punya **hitungan pemakaian** + waktu terakhir dipakai.
- **Proxy**: kelola daftar proxy (bulk `host:port` / `user:pass@host:port`),
  tombol **Tes dulu** (cek koneksi sebelum disimpan — yang mati otomatis tidak
  ditambahkan), cek hidup-mati lewat request nyata (latency + IP keluar), hapus,
  serta **hitungan pemakaian** per proxy.
  Posting bisa memakai rotasi proxy.
- Job runner background + log live (SSE).
- Posting bisa per akun atau **semua akun berurutan** (akun logout/error
  dilewati, akun lain tetap jalan) dengan **kuota berbeda per akun** — pilih
  "Semua akun" lalu isi jumlah posting masing-masing; **0 = akun dilewati**.
- **Jadwal**: posting otomatis pada jam tertentu (multi-jam, pilih hari),
  kuota per akun (A=10, B=5, …; **0 = akun dilewati**). Scheduler berjalan di
  dalam server, klaim slot sekali per hari (tidak dobel), toleransi telat 20
  menit, dan slot terlewat tidak dikejar.
- **Import cookie** kompatibel export extension Chrome: Cookie-Editor,
  EditThisCookie, maupun **Get cookies.txt LOCALLY** (Netscape: expiry `0`
  dianggap cookie sesi), header string, atau storage_state Playwright — bisa
  tempel atau pilih file `.json`/`.txt`.
- **Tes cookie sebelum simpan**: tombol *Tes cookie* di modal import membuka
  Carousell dengan cookie tersebut dan melaporkan login/nama akun tanpa
  menyimpan apa pun.
- **Deteksi login** berbasis header Carousell (ikon Inbox/Likes, tanpa tombol
  Masuk), nama akun diambil dari tombol `aria-label="Akun: <username>"`
  (fallback "Hello,"/Account). Browser memakai UA Chrome realistis +
  `AutomationControlled` dimatikan agar tidak kena challenge Cloudflare.
- **Kategori per akun (niche)**: atur `atasan_cowo` / `bawahan_cowo` /
  `atasan_cewe` / `bawahan_cewe` langsung di tabel Manajemen Akun (atau saat
  import cookie). Form posting dan jadwal punya opsi **Ikut kategori akun**,
  sehingga tiap akun otomatis mengambil listing sesuai niche-nya.
- **Hash routing** (`#accounts`, `#schedules`, …): refresh/bookmark tetap di
  halaman yang sama, tombol back jalan, dan halaman terakhir diingat.
- **Form jual Indonesia**: kategori "Fesyen Pria/Wanita → Atasan/Bawahan",
  kondisi "Digunakan dengan baik", ukuran "Ukuran", submit "Pasang sekarang".
  Deskripsi otomatis dibersihkan dari tautan/sebutan e-commerce (ditolak
  Carousell), sedangkan link Shopee tetap ditulis di **Opsi pengiriman**.
- **Anti-gugur Cloudflare**: kalau muncul Turnstile/challenge, akun otomatis
  ditandai `blocked` (badge "gugur"), sisa listing dilewati, dan akun tidak
  dipakai lagi sampai "Cek login" menunjukkan login valid.
- **Log dock footer** seperti terminal VS Code: muncul otomatis saat scrape/
  posting dari halaman mana pun, bisa ditarik naik-turun (tinggi diingat),
  dikecilkan, dibersihkan, dan tombol "Progres" untuk buka antrean. Tab baru
  mengikuti job yang sedang jalan; setelah tab ditutup/dibuka lagi, log job
  terakhir yang dilihat dipulihkan.
- **Halaman Pengaturan**: atur deskripsi, link Shopee di opsi pengiriman,
  harga min/max/kelipatan, dan kondisi. Default-nya mengikuti template project
  CLI (`upload.py`): `🆂hope` / `l!nk` dan link `s.shopee.co.id`. Ada pratinjau
  live hasil filter (baris "shopee"/"link" polos dibuang, versi obfuscated
  tetap lolos), serta tabel pemetaan kategori.
- **Logout di tengah proses**: kalau sesi akun mati saat posting, akun ditandai
  `logout`, listing yang sedang diproses gagal, sisa listing dilewati, dan run
  lanjut ke akun berikutnya.
- **Proxy rotating provider**: tambahkan endpoint HTTP rotating (dengan auth)
  seperti proxy biasa; IP keluar bisa berubah tiap request. Log posting
  menampilkan `IP: x.x.x.x (<label proxy / langsung>)` per listing.
- **Batal job**: tombol "Batal" di log dock (atau riwayat job) menghentikan
  posting/scrape yang sedang jalan. Item yang sedang diproses diselesaikan
  dulu, sisa listing tidak diubah, status job jadi `cancelled`.
- Cek login per akun dan rekap status.
- Konfigurasi di `config.json` (kategori, harga, deskripsi, selector kategori).

## Struktur

```
run.py                    # entrypoint web
config.json               # konfigurasi (dibuat dari config.example.json)
omnicaro/
  settings.py             # path, load/save config
  db.py                   # SQLite schema + query
  browser.py              # deteksi & launch browser cross-platform
  cookies.py              # normalisasi cookie -> storage_state
  authcheck.py            # cek status login
  scraper.py              # scrape listing + foto
  uploader.py             # isi form + submit listing
  queueing.py             # pembagian antrean per akun
  jobs.py                 # runner job + log stream
  web/server.py           # FastAPI
  web/static/             # UI
```

## Catatan

- Jalankan hanya untuk akun milik sendiri.
- Pola posting terlalu cepat dapat memicu pembatasan akun; atur `upload.delay_min/max`.
- Bila selector Carousell berubah, sesuaikan `upload.size_search`/`size_leaf` dan selector di `uploader.py`.
