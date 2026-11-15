#!/usr/bin/env bash
set -euo pipefail

DECK_USER="${SUDO_USER:-${USER:-deck}}"
if [[ ! "$DECK_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]]; then
    echo "[SwitchDeck] Error: invalid username '$DECK_USER'" >&2
    exit 1
fi

DECK_HOME="$(getent passwd "$DECK_USER" 2>/dev/null | cut -d: -f6 || true)"
if [ -z "$DECK_HOME" ]; then
    DECK_HOME="/home/$DECK_USER"
fi
DECK_UID="$(id -u "$DECK_USER" 2>/dev/null || echo 1000)"
RUNTIME_DIR="/run/user/${DECK_UID}"
DBUS_ADDR="unix:path=${RUNTIME_DIR}/bus"

echo "[SwitchDeck] Stopping service and unconditionally rebinding 28de:1205..."
if command -v systemctl >/dev/null 2>&1; then
    if [ "$(id -u)" -eq 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo -u "$DECK_USER" env HOME="$DECK_HOME" XDG_RUNTIME_DIR="$RUNTIME_DIR" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" systemctl --user disable --now switchdeckd.service 2>/dev/null || true
        else
            su -s /bin/bash "$DECK_USER" -c "HOME=\"$DECK_HOME\" XDG_RUNTIME_DIR=\"$RUNTIME_DIR\" DBUS_SESSION_BUS_ADDRESS=\"$DBUS_ADDR\" systemctl --user disable --now switchdeckd.service" 2>/dev/null || true
        fi
    else
        HOME="$DECK_HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$RUNTIME_DIR}" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-$DBUS_ADDR}" systemctl --user disable --now switchdeckd.service 2>/dev/null || true
    fi
fi

if [ -x "${DECK_HOME}/.local/bin/switchdeckctl" ]; then
    HOME="$DECK_HOME" XDG_RUNTIME_DIR="$RUNTIME_DIR" "${DECK_HOME}/.local/bin/switchdeckctl" rebind-builtin || true
fi

rm -f "${DECK_HOME}/.config/systemd/user/switchdeckd.service" \
      "${DECK_HOME}/.local/bin/switchdeckd" \
      "${DECK_HOME}/.local/bin/switchdeckctl" \
      "${DECK_HOME}/.config/wireplumber/wireplumber.conf.d/51-switchdeck-keepalive.conf"
rm -rf "${DECK_HOME}/.local/share/switchdeck"

SUDO_PREFIX=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO_PREFIX="sudo"
fi
$SUDO_PREFIX rm -f /usr/local/bin/switchdeck-helper /etc/sudoers.d/switchdeck /etc/atomic-update.conf.d/switchdeck.conf || true

echo "[SwitchDeck] Uninstalled cleanly."
