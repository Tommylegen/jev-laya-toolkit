# Jev Dashboard (lokal)

Dashboard web minimal untuk model **Jev** (TypeSafe AI — "System One" model).
Jev bukan model chat: kamu kirim satu `state` + sampai 8 pertanyaan bertipe,
dan dapat balik nilai terstruktur (`choice`, `score`, `noul`) yang bisa
di-branch langsung oleh kode. Dashboard ini = UI tipis di atas endpoint
`POST …/v1/systemone`.

## Jalankan

```bash
python3 server.py            # http://127.0.0.1:8791
# atau: python3 server.py --port 9000
# key untuk provider ber-key:
JEV_KEY=sk-... python3 server.py
```

(8787 dipakai layanan lain di mesin ini, jadi default-nya 8791.)

Butuh Python 3.10+ (stdlib saja, tanpa dependensi). Buka URL-nya di browser,
klik **▶ Jalankan** — contoh sudah terisi dan langsung jalan di route gratis.

## Provider

| Preset | URL | Key | Catatan |
|---|---|---|---|
| OpenCode Zen · `jev-1.13-free` | `https://opencode.ai/zen/v1/systemone` | tidak perlu | **Default.** Route anonim, gratis untuk waktu terbatas. Terverifikasi `HTTP 200` tanpa `Authorization`. |
| OpenCode Zen · `jev-1.13` | sama | perlu | Key dari opencode.ai. Tanpa key → `401 AuthError: Missing API key`. |
| jevmodel.org · `jev-latest` | `https://jevmodel.org/v1/systemone` | perlu (`sk-…`) | Pihak ketiga (bukan TypeSafe), akun baru dapat 100k input token gratis. |
| Custom | bebas | opsional | Endpoint SystemOne lain (mis. `api.typesafe.ai/v1/systemone`). |

Model kirim token input saja; output gratis (`usage.output_tokens` hanya laporan).
Bentuk jawaban per tipe: `choice` → `choice` + `probabilities` + `confidence`;
`score` → `score` + `confidence` (+ `legend`/`probabilities` di Zen);
`noul` → `noul` = P(ya) 0–1.

## Kenapa harus lewat proxy?

`opencode.ai/zen/v1/systemone` tidak mengirim header `Access-Control-Allow-*`
dan menjawab preflight `OPTIONS` dengan `404`, jadi `fetch` langsung dari
halaman web akan gagal. `server.py` menyajikan UI dan mem-proxy request dari
origin yang sama. Bonus: API key hanya perlu ada di environment server
(`JEV_KEY`) atau dikirim ke proxy lokal, bukan ke pihak ketiga dari browser.

## Isi folder

- `index.html` — UI (vanilla JS, tanpa build, tanpa CDN): tiga peran font
  (Fraunces untuk judul, Inter untuk antarmuka, JetBrains Mono untuk data),
  permukaan terpisah — kartu *Data*, kartu *Pertanyaan* (4 contoh: triage tiket /
  moderasi komentar / skoring lead / SMS spam, maks 8 pertanyaan), baris aksi,
  kartu *Hasil* (tile status·latensi·model·token, ringkasan, chart), drawer
  *Riwayat* yang bisa show/hide (sparkline latensi + tabel), dialog *Pengaturan*
  (route/model/key per-route/ambang YA) dan dialog JSON·cURL·Log.
  Bentuk chart: `choice` = bar peluang (pemenang hijau), `noul` = titik verdict +
  bilah dengan penanda ambang, `score` = sel per level (level terkuat disorot).
- `server.py` — server statis + proxy `/api/decide` (relay body upstream verbatim,
  plus header `X-Jev-Upstream-Ms` dan `X-Tokens-Remaining`).
- `start-laya.sh` — mount fs image Laya (kalau perlu) + jalankan `laya-serve`
  dengan cache & API key yang benar.
- `fonts/` — Fraunces (judul), Inter (antarmuka), JetBrains Mono (data),
  disajikan server dari `/fonts/*.woff2`; lisensi SIL OFL di `fonts/LICENSE-*.txt`.

## Laya self-host (wire-compatible dengan Jev)

Laya = model System One **pihak ketiga** (Convai Innovations, Apache-2.0) yang
menerima bentuk request/response `POST /v1/systemone` yang sama seperti Jev.
Dashboard ini sudah punya route **“Laya (self-host di VPS ini)”**.

Instalasi di VPS ini (karena filesystem root **kehabisan inode** — byte masih
~10 GB tapi inode bebas 0 — Laya dipasang di image ext4 sendiri):

```bash
# image 5 GB dengan 400k inode → /mnt/laya (sekali saja)
sudo fallocate -l 5G ~/laya-fs.img
sudo /sbin/mkfs.ext4 -q -N 400000 -m 0 ~/laya-fs.img
sudo mkdir -p /mnt/laya
sudo losetup -f --show ~/laya-fs.img        # catat /dev/loopN
sudo mount /dev/loopN /mnt/laya && sudo chown $USER /mnt/laya
mkdir -p /mnt/laya/{tmp,hf}

# venv + paket (semua di dalam image)
export TMPDIR=/mnt/laya/tmp HF_HUB_CACHE=/mnt/laya/hf
python3 -m venv /mnt/laya/venv
/mnt/laya/venv/bin/pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
/mnt/laya/venv/bin/pip install --no-cache-dir "laya[serve]"      # → laya 0.4.8, torch 2.14.1+cpu
```

Menjalankan / menghentikan server:

```bash
./start-laya.sh                 # preload checkpoint EN + multilingual, bind 127.0.0.1:8000
pkill -f laya-serve             # stop
```

**Port 8000 bukan halaman web** — itu API (FastAPI). `GET /` menjawab
`{"detail":"Not Found"}`; yang tersedia: `POST /v1/systemone`,
`POST /v1/systemone/batch`, `GET /health`, dan dokumentasi interaktif di
**http://127.0.0.1:8000/docs**. Dashboard-nya adalah halaman ini sendiri
(`server.py`, port 8791) dengan route “Laya (self-host di VPS ini)”.

**Key Laya diisi otomatis**: proxy dashboard membaca `~/.laya_key` dan hanya
menyuntikkannya untuk upstream loopback Laya (`127.0.0.1:8000` / `localhost:8000`)
— jadi pilih route Laya, klik Jalankan, tanpa menempel key di browser. Route lain
tidak pernah menerima key itu. (Dashboard juga menyimpan API key **per-route**,
supaya key satu provider tidak ikut terkirim ke provider lain.)

Default bind `127.0.0.1` (loopback). Kalau perlu diakses dari mesin lain:
`LAYA_HOST=0.0.0.0 ./start-laya.sh` — jangan lupa key tetap aktif dan port
dibatasi firewall.

API key disimpan di `~/.laya_key` (server memakai `LAYA_API_KEY` darinya; tanpa
header `Authorization: Bearer <key>` endpoint menjawab **401**). Karena default
bind-nya loopback, port 8000 tidak terbuka ke internet — kalau kamu ubah ke
`0.0.0.0`, key itu wajib dan sebaiknya port dibatasi firewall.

Contoh pemakaian:

```bash
KEY=$(cat ~/.laya_key)

# HTTP (bentuk request sama dengan Jev)
curl -s localhost:8000/v1/systemone -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{
    "state": "The customer was billed twice and wants a refund today.",
    "questions": {
      "route": {"type":"choice","instructions":"Which queue?",
                "criteria":{"billing":"payments","technical":"errors","sales":"pricing"}},
      "escalate": {"type":"noul","instructions":"Does this need a human now?"},
      "urgency": {"type":"score","instructions":"How urgent?",
                  "criteria":["routine","soon","urgent","critical"]}}}'

# Python SDK (langsung, tanpa server) — pakai venv di image
HF_HUB_CACHE=/mnt/laya/hf /mnt/laya/venv/bin/python - <<'PY'
from laya import Router
r = Router(preload=True)
print(r.predict("Refund my duplicate charge", {"dept": {"type":"choice",
      "instructions":"Which department?", "criteria":{"billing":"payments","tech":"bugs"}}}))
PY

# CLI
/mnt/laya/venv/bin/laya "My payment failed twice" --preset triage --predict
/mnt/laya/venv/bin/laya --batch tickets.txt --predict --json
```

Catatan penting:

- **Akurasi**: checkpoint English zero-shot jauh di bawah Jev pada kasus yang
  sama (contoh terukur: tiket refund ganda → Jev “perlu manusia” 88%, Laya 0,2%).
  Benchmark penulisnya: 0.362 (base) vs **0.766** setelah fine-tune di
  typed-decisions. Untuk produksi: fine-tune dengan data sendiri.
- Saat load, checkpoint melaporkan *“invalid temperatures … treat confidence
  from the affected entries as uncalibrated”* untuk sebagian entri `choice` —
  jangan pakai `confidence` Laya sebagai gerbang keputusan tanpa kalibrasi.
- Batas konteks kecil: 512 token (English) / 1024–8192 (multilingual,
  `max_len=8192`). Teks panjang perlu checkpoint multilingual.
- Router otomatis memilih checkpoint berdasarkan skrip/bahasa (`routing.model`
  di response); teks Indonesia masuk ke checkpoint multilingual.

Akses dari HP di jaringan yang sama: `python3 server.py --host 0.0.0.0` lalu buka
`http://<ip-vps>:8791` — sadari bahwa ini membuka dashboard ke jaringan tersebut
(tanpa autentikasi), jadi pakai hanya di jaringan tepercaya.

## Contoh curl (route gratis, tanpa key)

```bash
curl -sS -X POST https://opencode.ai/zen/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{"model":"jev-1.13-free",
       "state":"The customer has been billed twice and wants a refund today.",
       "questions":{
         "route":{"type":"choice","instructions":"Which queue should own this ticket?",
                  "criteria":{"billing":"Payments, refunds, invoices","technical":"Product errors"}},
         "escalate":{"type":"noul","instructions":"Does this need a human right now?"},
         "urgency":{"type":"score","instructions":"How urgent?","criteria":["routine","soon","urgent","critical"]}}}'
```

## Batasan

- Route gratis `jev-1.13-free` adalah penawaran sementara pihak OpenCode; kalau
  mati, ganti preset dan pindah ke provider ber-key (kolom key / `JEV_KEY`).
- Proxy mengirim User-Agent browser. Cloudflare di `opencode.ai` memblokir UA
  default Python (`urllib`) dengan HTTP 403 `error 1010 browser_signature_banned`;
  `curl` dan UA browser lolos. Override lewat env `JEV_UA` bila perlu.
- Batas API: 8 pertanyaan per request, `instructions` ≤1800 karakter,
  `criteria` choice 2–20 opsi / score 2–10 level.
- `server.py` untuk pemakaian lokal; jangan expose ke jaringan publik tanpa
  menambah autentikasi dan allowlist URL upstream.
