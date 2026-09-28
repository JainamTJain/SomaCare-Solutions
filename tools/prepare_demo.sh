#!/usr/bin/env bash
# Compress the newest raw demo clip, record the replay with the real pipeline, and put the
# results where the website serves them. Run from the repo root:
#   SHOW_VIDEO=1 bash tools/prepare_demo.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW_DIR="$ROOT/demo_media/video/raw"
OUT_VID="$ROOT/demo_media/video/bed1.mp4"
CALIB_WINDOWS="${CALIB_WINDOWS:-supine:5-18,left30:45-80,right30:110-145}"
TIME_SCALE="${TIME_SCALE:-60}"
MAX_MB="${MAX_MB:-40}"

command -v ffmpeg >/dev/null || { echo "ffmpeg not found. Install it (brew install ffmpeg / apt install ffmpeg)."; exit 1; }
RAW="$(ls -t "$RAW_DIR"/* 2>/dev/null | head -n1 || true)"
[ -n "$RAW" ] || { echo "No clip found in demo_media/video/raw/. Put your phone video there first."; exit 1; }

echo "Compressing $RAW"
ffmpeg -y -loglevel error -i "$RAW" -vf "scale=-2:720" -c:v libx264 -crf 28 -preset slow -an -movflags +faststart "$OUT_VID"
SIZE_MB=$(( $(wc -c < "$OUT_VID") / 1048576 ))
[ "$SIZE_MB" -le "$MAX_MB" ] || { echo "Compressed clip is ${SIZE_MB} MB (limit ${MAX_MB}). Trim the clip or raise -crf."; exit 1; }
echo "Compressed to ${SIZE_MB} MB -> demo_media/video/bed1.mp4"

mkdir -p "$ROOT/web/public/demo"
cd "$ROOT/backend"
python tools/record_replay.py --video "$OUT_VID" --time-scale "$TIME_SCALE" \
  --calib-windows "$CALIB_WINDOWS" --script tools/demo_script.json \
  --photos "$ROOT/demo_media/photos" --out "$ROOT/web/public/demo/replay.json"

if [ "${SHOW_VIDEO:-0}" = "1" ]; then
  cp "$OUT_VID" "$ROOT/web/public/demo/bed1-demo.mp4"
  echo "Copied clip to web/public/demo/bed1-demo.mp4 (this file is PUBLIC on the website)."
fi
echo "Done. Commit web/public/demo/replay.json (and bed1-demo.mp4 if SHOW_VIDEO=1), then push."
