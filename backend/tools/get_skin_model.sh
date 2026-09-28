#!/usr/bin/env bash
# Download the published pressure-ulcer model weights (351 MB, MIT licence) and verify them.
# Source: https://github.com/Joy-Diganta/pressure-ulcer-classifier (best_model_fold0.pth, Git LFS)
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="models/pu_convnextv2_fold0.pth"
SHA="06887f14fe1206e403c35a381129d2d883d79c0219cde564ed10d6840f45e155"
URL="https://media.githubusercontent.com/media/Joy-Diganta/pressure-ulcer-classifier/main/best_model_fold0.pth"
mkdir -p models
sha() { if command -v sha256sum >/dev/null; then sha256sum "$1" | cut -d' ' -f1; else shasum -a 256 "$1" | cut -d' ' -f1; fi; }
if [ -f "$OUT" ] && [ "$(sha "$OUT")" = "$SHA" ]; then echo "Already downloaded and verified: $OUT"; exit 0; fi
echo "Downloading 351 MB..."
if ! curl -L --fail --progress-bar -o "$OUT" "$URL"; then
  echo "Direct download failed, trying git lfs..."
  command -v git-lfs >/dev/null || { echo "Install git-lfs (brew install git-lfs) and re-run."; exit 1; }
  TMP="$(mktemp -d)"; git clone --depth 1 https://github.com/Joy-Diganta/pressure-ulcer-classifier.git "$TMP/puc"
  (cd "$TMP/puc" && git lfs pull --include best_model_fold0.pth); cp "$TMP/puc/best_model_fold0.pth" "$OUT"; rm -rf "$TMP"
fi
GOT="$(sha "$OUT")"
if [ "$GOT" != "$SHA" ]; then echo "Checksum mismatch ($GOT). Deleting the file."; rm -f "$OUT"; exit 1; fi
echo "Verified: $OUT"
