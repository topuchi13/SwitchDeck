#!/usr/bin/env bash
set -euo pipefail

# One-command macOS -> Steam Deck rsync deploy and service restart.
# Usage: ./scripts/deploy_deck.sh [deck@steamdeck.local]

TARGET="${1:-deck@steamdeck.local}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[SwitchDeck] Syncing ${REPO_DIR} -> ${TARGET}:~/switchdeck-src ..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '*.pyc' \
    --exclude 'node_modules' --exclude 'dist-zip' --exclude 'build' \
    --exclude 'preview' --exclude 'RESEARCH_AND_ACTION_PLAN.md' --exclude 'tsconfig.preview.json' \
    --exclude 'docs' --exclude '.github' --exclude '.DS_Store' --exclude '*.map' \
    "${REPO_DIR}/" "${TARGET}:~/switchdeck-src/"

ssh -t "$TARGET" "cd ~/switchdeck-src && bash ./scripts/install.sh && ~/.local/bin/switchdeckctl doctor"
