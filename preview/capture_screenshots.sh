#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREVIEW_DIR="$ROOT_DIR/preview"
SHOT_DIR="$PREVIEW_DIR/screenshots"
CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  if [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
    CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  else
    CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
  fi
fi

if [ -z "$CHROME" ] || [ ! -x "$CHROME" ]; then
  echo "ERROR: Google Chrome/Chromium not found" >&2
  exit 1
fi

cd "$ROOT_DIR"
npm run preview

mkdir -p "$SHOT_DIR"

capture() {
  local scenario="$1"
  local width="$2"
  local height="$3"
  local out="$SHOT_DIR/${scenario}_${width}x${height}.png"
  local url="file://${PREVIEW_DIR}/index.html?scenario=${scenario}"

  echo "[SwitchDeck] Capturing $scenario (${width}x${height}) -> $out"
  "$CHROME" \
    --headless=new \
    --disable-gpu \
    --no-sandbox \
    --hide-scrollbars \
    --virtual-time-budget=2500 \
    --window-size="${width},${height}" \
    --screenshot="$out" \
    "$url" >/dev/null 2>&1
}

capture "handheld" 1280 800
capture "docked_s90c" 1920 1080
capture "docked_warning" 1920 1080
capture "tv_pairing" 1280 800
capture "docked_overclock" 1920 1080

ls -lh "$SHOT_DIR"
