#!/usr/bin/env bash
set -euo pipefail

# One-command macOS -> Steam Deck rsync deploy and service restart.
# Usage: ./scripts/deploy_deck.sh [deck@steamdeck.local]

TARGET="${1:-deck@steamdeck.local}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[SwitchDeck] Syncing ${REPO_DIR} -> ${TARGET}:~/switchdeck-src ..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
    "${REPO_DIR}/" "${TARGET}:~/switchdeck-src/"

ssh -t "$TARGET" "cd ~/switchdeck-src && bash ./scripts/install.sh && ~/.local/bin/switchdeckctl doctor"
