# Deploy omnicaro di VPS

Dokumen ini menjelaskan cara men-deploy **omnicaro** (dashboard web otomasi
Carousell) ke VPS Linux dari nol: instalasi, konfigurasi, systemd, Nginx,
HTTPS, backup, update, dan troubleshooting.

> Ringkas: satu proses Python (`run.py`) menjalankan web + job runner +
> penjadwal. Browser otomasi (Playwright + Chromium/Brave) dijalankan oleh
> proses yang sama. **Wajib satu worker.**

---

## 1. Arsitektur singkat

```
Browser (kamu)
   │ HTTPS + Basic Auth
   ▼
Nginx (port 80/443)  ──►  127.0.0.1:8080  (uvicorn/FastAPI, run.py)
                              ├── web UI statis (HTML/CSS/JS)
                              ├── REST API + SSE log
                              ├── job runner (scrape/upload/check)
                              ├── scheduler thread (jadwal posting)
                              └── Playwright + Chromium/Brave
                                      │
                                      └── data/ (SQLite, gambar, log, cookie)
```

Komponen yang perlu dipahami saat deploy:

| Komponen | Lokasi | Catatan |
|---|---|---|
| Entry point | `run.py` | host/port dari `config.json` |
| Web + API | `omnicaro/web/server.py` | FastAPI |
| Job runner | `omnicaro/jobs.py` | **satu thread worker** |
| Penjadwal | `omnicaro/scheduler.py` | cek slot tiap 20 detik, waktu lokal |
| Browser | `omnicaro/browser.py` | deteksi Brave/Chrome/Chromium/Edge |
| Database | `data/omnicaro.db` | SQLite (WAL) |
| Gambar | `data/images/` | hasil scrape |
| Log job | `data/jobs/` | satu file per job |
| Log server | `data/server.log` | stdout uvicorn diarahkan ke sini |
| Config | `config.json` | dibuat dari `config.example.json` |

---

## 2. Prasyarat VPS

**Minimum:** 2 vCPU, 2 GB RAM, 20 GB disk.
**Disarankan:** 2–4 vCPU, 4 GB RAM, 40 GB+ disk (gambar listing cepat menumpuk).

- OS: Ubuntu 22.04 / 24.04 (Debian 12 juga OK).
- Bandwidth: scrape + upload foto memakai kuota; 500 GB/bulan cukup untuk
  ratusan listing, tapi perhatikan retry yang mengulang unduhan.
- Akses root/sudo dan port 22 terbuka.

```bash
sudo apt update && sudo apt upgrade -y
sudo timedatectl set-timezone Asia/Jakarta   # penjadwal pakai waktu lokal
```

> Zona waktu penting: jadwal posting (`07:00`, `12:00`, dst) mengikuti jam
> server. Set dulu sebelum membuat jadwal.

---

## 3. Buat user & folder aplikasi

Jangan jalankan sebagai root. Chromium/Playwright juga lebih aman sebagai user
biasa.

```bash
sudo adduser --disabled-password --gecos "" omnicaro
sudo mkdir -p /opt/omnicaro
sudo chown omnicaro:omnicaro /opt/omnicaro
sudo -iu omnicaro
```

Semua perintah berikut dijalankan sebagai user `omnicaro` (kecuali ditandai
`sudo`).

---

## 4. Install dependency sistem

```bash
sudo apt install -y python3 python3-venv python3-pip git curl \
  build-essential libssl-dev libffi-dev
```

Untuk library browser (wajib, kalau tidak Chromium gagal start):

```bash
# setelah venv + playwright terpasang (langkah 5), jalankan:
playwright install-deps chromium
```

Kalau ingin memakai Chromium dari apt (bukan unduhan Playwright):

```bash
sudo apt install -y chromium
```

Brave opsional:

```bash
# contoh repo resmi Brave (Ubuntu)
sudo curl -fsSLo /usr/share/keyrings/brave-browser-archive-keyring.gpg \
  https://brave-browser-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/brave-browser-archive-keyring.gpg] \
https://brave-browser-apt-release.s3.brave.com/ stable main" | \
  sudo tee /etc/apt/sources.list.d/brave-browser-release.list
sudo apt update && sudo apt install -y brave-browser
```

`omnicaro` mendeteksi otomatis `/usr/bin/brave-browser`, `/usr/bin/chromium`,
`/usr/bin/google-chrome`, dst. Kalau path-nya beda, set di `config.json`
(`browser.executable`) atau env `OMNICARO_BROWSER`.

---

## 5. Clone & install Python

```bash
cd /opt/omnicaro
git clone https://github.com/DioSaputra28/omnicaro.git .
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
playwright install-deps chromium   # butuh sudo
```

Cek Playwright melihat browser:

```bash
python -c "from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    print('ok', b.version)
    b.close()"
```

---

## 6. Konfigurasi

```bash
cp config.example.json config.json
nano config.json
```

Bagian penting:

```jsonc
{
  "server": { "host": "127.0.0.1", "port": 8080 },
  "browser": {
    "executable": "",      // kosong = deteksi otomatis
    "headless": true       // VPS tanpa desktop: biarkan true
  },
  "scrape": {
    "base_url": "https://www.carousell.com.my",
    "max_photos": 3,
    "delay_ms": 300,
    "categories": { /* atasan_cowo, bawahan_cowo, atasan_cewe, bawahan_cewe */ }
  },
  "upload": {
    "target": "https://id.carousell.com",
    "price_min": 40000,
    "price_max": 60000,
    "price_step": 1000,
    "condition": "Digunakan dengan baik",
    "description": "...template deskripsi...",
    "delivery": "check out here: https://s.shopee.co.id/...",
    "size_search": { "atasan_cowo": "Fesyen Pria", ... },
    "size_leaf":   { "atasan_cowo": "Atasan", ... }
  }
}
```

Catatan:

- `server.host` **harus** `127.0.0.1` kalau pakai Nginx. Jangan bind `0.0.0.0`
  ke internet tanpa autentikasi.
- Template deskripsi/delivery juga bisa diubah dari halaman **Pengaturan**
  setelah web jalan.
- `data/` dan `config.json` tidak masuk git; keduanya milik server ini.

---

## 7. Jalankan manual (tes pertama)

```bash
cd /opt/omnicaro
source .venv/bin/activate
python run.py
```

Output log ada di `data/server.log`. Buka dari komputer lokal lewat SSH tunnel:

```bash
ssh -L 8080:127.0.0.1:8080 omnicaro@IP_VPS
```

Lalu buka `http://127.0.0.1:8080`.

**Urutan onboarding:**

1. **Manajemen Akun → Import cookie** (export dari Cookie-Editor / Get
   cookies.txt LOCALLY), isi kategori/niche. Klik **Tes cookie** sebelum simpan.
2. **Katalog** → pilih kategori → **Mulai scrape**. Pantau di log dock footer.
3. **Pengaturan** → pastikan deskripsi, link Shopee, harga, kondisi.
4. **Progres & Antrean** → pilih **Semua akun** + kategori **Ikut kategori
   akun** → **Mulai posting**.
5. Opsional: **Jadwal** untuk posting otomatis per jam.

---

## 8. systemd (auto-start & restart)

Buat service:

```bash
sudo nano /etc/systemd/system/omnicaro.service
```

```ini
[Unit]
Description=omnicaro - Carousell web automation
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=omnicaro
Group=omnicaro
WorkingDirectory=/opt/omnicaro
Environment=PYTHONUNBUFFERED=1
# Environment=OMNICARO_BROWSER=/usr/bin/chromium
ExecStart=/opt/omnicaro/.venv/bin/python /opt/omnicaro/run.py
Restart=always
RestartSec=5
TimeoutStopSec=30
# batasi agar tidak liar
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now omnicaro
sudo systemctl status omnicaro
sudo journalctl -u omnicaro -f
```

**Jangan** menjalankan `uvicorn --workers N` atau multiple instance. Alasannya:

- job runner memakai antrean di memori → dobel eksekusi;
- scheduler bisa mengklaim slot yang sama di dua proses;
- SQLite menulis dari banyak proses (WAL membantu, tapi tetap hindari).

---

## 9. Nginx reverse proxy + Basic Auth

Web ini mengelola cookie akun Carousell. **Jangan expose tanpa autentikasi.**

```bash
sudo apt install -y nginx apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

`/etc/nginx/sites-available/omnicaro`:

```nginx
server {
    listen 80;
    server_name panel.contoh.com;

    auth_basic "omnicaro";
    auth_basic_user_file /etc/nginx/.htpasswd;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Penting untuk SSE log dock: tanpa ini log bisa tertahan
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        add_header X-Accel-Buffering no;
    }
}
```

Aktifkan:

```bash
sudo ln -s /etc/nginx/sites-available/omnicaro /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

HTTPS gratis:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d panel.contoh.com
```

Firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

Jangan buka port 8080 ke publik.

---

## 10. Data, backup, dan pemulihan

Semua state ada di `/opt/omnicaro/data`:

```
data/
├── omnicaro.db        # akun (cookie!), listing, uploads, UA, proxy, jadwal
├── omnicaro.db-wal    # WAL SQLite
├── images/            # foto listing
├── states/            # storage_state per akun (jika ada)
├── jobs/              # log per job
└── server.log
```

**File ini sensitif** — berisi cookie sesi Carousell dalam plaintext.

```bash
chmod 700 /opt/omnicaro/data
chmod 600 /opt/omnicaro/data/omnicaro.db /opt/omnicaro/config.json
```

Backup harian (contoh cron jam 03:00):

```bash
mkdir -p /opt/backup
cat > /opt/omnicaro/backup.sh <<'SH'
#!/usr/bin/env bash
set -euo pipefail
ts=$(date +%F)
mkdir -p /opt/backup/$ts
sqlite3 /opt/omnicaro/data/omnicaro.db ".backup '/opt/backup/$ts/omnicaro.db'"
rsync -a --delete /opt/omnicaro/data/images/ /opt/backup/$ts/images/
cp /opt/omnicaro/config.json /opt/backup/$ts/config.json
find /opt/backup -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
SH
chmod +x /opt/omnicaro/backup.sh
```

```bash
crontab -e
# 0 3 * * * /opt/omnicaro/backup.sh >> /opt/omnicaro/data/backup.log 2>&1
```

Restore: stop service → taruh DB + images kembali → start service.

---

## 11. Update aplikasi

```bash
cd /opt/omnicaro
sudo systemctl stop omnicaro
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium        # kalau versi Playwright berubah
sudo systemctl start omnicaro
```

Kalau ada perubahan schema, migrasi SQLite berjalan otomatis saat start
(`init_db` menambah kolom yang belum ada).

---

## 12. Log & monitoring

- Log aplikasi: `tail -f /opt/omnicaro/data/server.log`
- Log service: `journalctl -u omnicaro -f`
- Log per job: `data/jobs/<id>.log` (juga tampil di log dock web)
- Health check:

```bash
curl -fsS http://127.0.0.1:8080/api/state > /dev/null && echo OK
```

Log rotation sederhana (hindari `server.log` membengkak):

```bash
sudo tee /etc/logrotate.d/omnicaro >/dev/null <<'EOF'
/opt/omnicaro/data/server.log {
  weekly
  rotate 4
  compress
  missingok
  notifempty
  copytruncate
}
EOF
```

---

## 13. Troubleshooting

**`Failed to fetch` di UI**
Server mati atau port salah. Cek `systemctl status omnicaro` dan
`data/server.log`.

**Cloudflare Turnstile / "Tunggu sebentar..."**
Akun otomatis ditandai `gugur (CF)` dan dilewati. Coba:
- pakai proxy di halaman Proxy (centang rotasi saat posting),
- pastikan server tidak membuka banyak akun terlalu cepat,
- `headless: false` + Xvfb hanya untuk debugging:

```bash
sudo apt install -y xvfb
xvfb-run -a /opt/omnicaro/.venv/bin/python /opt/omnicaro/run.py
```

**Chromium gagal start / missing libraries**

```bash
playwright install-deps chromium
```

**“Browser was not found at the specified executablePath”**
Path di `browser.executable` salah. Kosongkan agar deteksi otomatis, atau isi
path yang benar (`which chromium`).

**SQLite `database is locked`**
Pastikan hanya satu proses omnicaro. Jangan jalankan service + `python run.py`
bersamaan.

**Job berhenti mendadak / memori penuh**
Chromium butuh 300–600 MB per instance. Naikkan RAM atau kurangi jumlah akun
per run. Cek `dmesg | tail` untuk OOM killer.

**Jam jadwal tidak sesuai**
Set timezone server (`timedatectl set-timezone Asia/Jakarta`), lalu restart
service.

**Posting dobel**
Pastikan satu worker, dan jangan menjalankan dua instance (systemd + manual).

**Gambar menumpuk**
Backup lalu bersihkan `data/images` yang sudah tidak diperlukan; listing yang
sudah `posted` tidak memakai gambar lagi.

---

## 14. Checklist deploy

- [ ] User non-root + folder `/opt/omnicaro`
- [ ] Python venv + `requirements.txt`
- [ ] `playwright install chromium` + `install-deps`
- [ ] `config.json` dari `config.example.json`
- [ ] `server.host = 127.0.0.1`
- [ ] Timezone server sesuai (mis. Asia/Jakarta)
- [ ] systemd aktif + auto-restart
- [ ] Nginx + Basic Auth + HTTPS
- [ ] Firewall hanya 22/80/443
- [ ] `data/` permission 700, backup harian
- [ ] Tes: import cookie → tes cookie → scrape → posting 1 akun
- [ ] Jadwal diuji dengan jam beberapa menit ke depan
