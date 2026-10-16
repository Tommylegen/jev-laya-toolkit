#!/usr/bin/env bash
# start-laya.sh — jalankan Laya (self-host) untuk dashboard SystemOne.
#
# Isi:
#   1. Mount image fs (~/laya-fs.img → /mnt/laya) kalau belum ter-mount.
#      Image ini dipakai karena filesystem root VPS kehabisan *inode*:
#      byte masih ~10 GB, tapi tidak ada inode baru untuk menulis file kecil.
#   2. Jalankan `laya-serve` (endpoint Jev-compatible: POST /v1/systemone).
#
# Pakai:
#   ./start-laya.sh                  # preload checkpoint EN + multilingual
#   LAYA_PRELOAD=0 ./start-laya.sh   # lazy (hemat RAM, load saat request pertama)
#   LAYA_DEVICE=cuda ./start-laya.sh # kalau ada GPU
#
set -euo pipefail
IMG="${LAYA_IMG:-$HOME/laya-fs.img}"
MNT="${LAYA_MNT:-/mnt/laya}"
VENV="$MNT/venv"

if ! grep -q " $MNT " /proc/self/mountinfo; then
  echo "→ mount $IMG ke $MNT"
  DEV="$(sudo losetup -j "$IMG" | cut -d: -f1 | head -1 || true)"
  [ -n "$DEV" ] || DEV="$(sudo losetup -f --show "$IMG")"
  sudo mount "$DEV" "$MNT"
  sudo chown "$(id -un):$(id -gn)" "$MNT"
fi

export HF_HUB_CACHE="$MNT/hf"
export TMPDIR="$MNT/tmp"
export LAYA_DEVICE="${LAYA_DEVICE:-cpu}"
export LAYA_PRELOAD="${LAYA_PRELOAD:-1}"
# Bind ke loopback secara default: port 8000 adalah API saja (bukan halaman web),
# dan dashboard memanggilnya dari proxy lokal di host yang sama. Kalau memang perlu
# diakses dari mesin lain: LAYA_HOST=0.0.0.0 ./start-laya.sh (pastikan key tetap aktif).
export LAYA_HOST="${LAYA_HOST:-127.0.0.1}"
export LAYA_PORT="${LAYA_PORT:-8000}"
if [ -f "$HOME/.laya_key" ]; then
  export LAYA_API_KEY="$(cat "$HOME/.laya_key")"
fi

echo "→ laya-serve di $LAYA_HOST:$LAYA_PORT (device=$LAYA_DEVICE, preload=$LAYA_PRELOAD, auth=$([ -n "${LAYA_API_KEY:-}" ] && echo ya || echo tidak))"
echo "  API: POST http://$LAYA_HOST:$LAYA_PORT/v1/systemone · docs: http://$LAYA_HOST:$LAYA_PORT/docs"
exec "$VENV/bin/laya-serve" "$@"
