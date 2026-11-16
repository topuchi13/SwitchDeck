#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STAGE_ROOT="$ROOT_DIR/build"
STAGE_DIR="$STAGE_ROOT/SwitchDeck"
ZIP_DIR="$ROOT_DIR/dist-zip"
ZIP_PATH="$ZIP_DIR/SwitchDeck.zip"

echo "[SwitchDeck] Building Decky frontend bundle..."
npm run build

echo "[SwitchDeck] Staging package in $STAGE_DIR..."
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/py_modules" "$ZIP_DIR"

cp "$ROOT_DIR/plugin.json" "$STAGE_DIR/"
cp "$ROOT_DIR/package.json" "$STAGE_DIR/"
cp "$ROOT_DIR/main.py" "$STAGE_DIR/"
[ -f "$ROOT_DIR/LICENSE" ] && cp "$ROOT_DIR/LICENSE" "$STAGE_DIR/"

cp -R "$ROOT_DIR/dist" "$STAGE_DIR/dist"
cp -R "$ROOT_DIR/src/switchdeck" "$STAGE_DIR/py_modules/switchdeck"

find "$STAGE_DIR" -name ".DS_Store" -type f -delete
find "$STAGE_DIR/dist" -name "*.map" -type f -delete
find "$STAGE_DIR/py_modules" -name "__pycache__" -type d -prune -exec rm -rf {} +
find "$STAGE_DIR/py_modules" -name "*.pyc" -type f -delete

rm -f "$ZIP_DIR"/SwitchDeck*.zip
(
  cd "$STAGE_ROOT"
  zip -qr "$ZIP_PATH" "SwitchDeck"
)

echo "[SwitchDeck] Created $ZIP_PATH"
ls -lh "$ZIP_PATH"
