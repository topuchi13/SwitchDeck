#!/usr/bin/env bash
set -euo pipefail

# Installs SwitchDeck in user space (~/.local/share/switchdeck) + user systemd
# plus minimal root sysfs helper preserved across SteamOS atomic updates.

DECK_USER="${SUDO_USER:-${USER:-deck}}"
if [[ ! "$DECK_USER" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]]; then
    echo "[SwitchDeck] Error: invalid username '$DECK_USER'" >&2
    exit 1
fi

DECK_HOME="$(getent passwd "$DECK_USER" 2>/dev/null | cut -d: -f6 || true)"
if [ -z "$DECK_HOME" ]; then
    DECK_HOME="/home/$DECK_USER"
fi
DECK_UID="$(id -u "$DECK_USER" 2>/dev/null || echo 1000)"
DECK_GID="$(id -g "$DECK_USER" 2>/dev/null || echo 1000)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${DECK_HOME}/.local/share/switchdeck"
BIN_DIR="${DECK_HOME}/.local/bin"
SYSTEMD_USER_DIR="${DECK_HOME}/.config/systemd/user"

run_as_deck_user() {
    if [ "$(id -u)" -eq 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo -u "$DECK_USER" -H "$@"
        else
            su -s /bin/bash "$DECK_USER" -c "$(printf '%q ' "$@")"
        fi
    else
        "$@"
    fi
}

echo "[SwitchDeck] Installing for user '${DECK_USER}' into ${APP_DIR}..."
run_as_deck_user mkdir -p "${APP_DIR}/src" "$BIN_DIR" "$SYSTEMD_USER_DIR"
run_as_deck_user rm -rf "${APP_DIR}/src/switchdeck"
run_as_deck_user cp -r "${REPO_DIR}/src/switchdeck" "${APP_DIR}/src/"
run_as_deck_user cp "${REPO_DIR}/pyproject.toml" "$APP_DIR/"
run_as_deck_user find "${APP_DIR}/src/switchdeck" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

run_as_deck_user tee "${BIN_DIR}/switchdeckd" >/dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${APP_DIR}/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec /usr/bin/python3 -m switchdeck.daemon "\$@"
EOF

run_as_deck_user tee "${BIN_DIR}/switchdeckctl" >/dev/null <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${APP_DIR}/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec /usr/bin/python3 -m switchdeck.cli "\$@"
EOF
run_as_deck_user chmod +x "${BIN_DIR}/switchdeckd" "${BIN_DIR}/switchdeckctl"

run_as_deck_user tee "${SYSTEMD_USER_DIR}/switchdeckd.service" >/dev/null <<EOF
[Unit]
Description=SwitchDeck Universal Docking Daemon
After=graphical-session.target pipewire.service wireplumber.service

[Service]
Type=simple
ExecStart=${BIN_DIR}/switchdeckd
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF

# Install privileged helper + SteamOS atomic-update preservation (requires sudo)
SUDO_PREFIX=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO_PREFIX="sudo"
fi

$SUDO_PREFIX install -o 0 -g 0 -m 0755 "${REPO_DIR}/scripts/switchdeck-helper" /usr/local/bin/switchdeck-helper

SUDOERS_TMP="$(mktemp)"
cleanup_sudoers_tmp() {
    rm -f "$SUDOERS_TMP"
}
trap cleanup_sudoers_tmp EXIT

cat > "$SUDOERS_TMP" <<EOF
Defaults!/usr/local/bin/switchdeck-helper env_reset, always_set_home, !setenv, secure_path="/usr/sbin:/usr/bin:/sbin:/bin"
${DECK_USER} ALL=(root) NOPASSWD: /usr/local/bin/switchdeck-helper *
EOF
chmod 0440 "$SUDOERS_TMP"

VISUDO_BIN="$(command -v visudo || command -v /usr/sbin/visudo || command -v /sbin/visudo || true)"
if [ -n "$VISUDO_BIN" ]; then
    "$VISUDO_BIN" -cf "$SUDOERS_TMP"
elif [ -n "$SUDO_PREFIX" ]; then
    $SUDO_PREFIX visudo -cf "$SUDOERS_TMP"
else
    echo "[SwitchDeck] Error: visudo not found; refusing to install unvalidated sudoers rule" >&2
    exit 1
fi

$SUDO_PREFIX install -o 0 -g 0 -m 0440 "$SUDOERS_TMP" /etc/sudoers.d/switchdeck

$SUDO_PREFIX mkdir -p /etc/atomic-update.conf.d
cat <<'EOF' | $SUDO_PREFIX tee /etc/atomic-update.conf.d/switchdeck.conf >/dev/null
/usr/local/bin/switchdeck-helper
/etc/sudoers.d/switchdeck
EOF

if command -v systemctl >/dev/null 2>&1; then
    RUNTIME_DIR="/run/user/${DECK_UID}"
    DBUS_ADDR="unix:path=${RUNTIME_DIR}/bus"
    if [ "$(id -u)" -eq 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo -u "$DECK_USER" env HOME="$DECK_HOME" XDG_RUNTIME_DIR="$RUNTIME_DIR" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" systemctl --user daemon-reload && \
            sudo -u "$DECK_USER" env HOME="$DECK_HOME" XDG_RUNTIME_DIR="$RUNTIME_DIR" DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR" systemctl --user enable --now switchdeckd.service || true
        else
            su -s /bin/bash "$DECK_USER" -c "HOME=\"$DECK_HOME\" XDG_RUNTIME_DIR=\"$RUNTIME_DIR\" DBUS_SESSION_BUS_ADDRESS=\"$DBUS_ADDR\" systemctl --user daemon-reload && HOME=\"$DECK_HOME\" XDG_RUNTIME_DIR=\"$RUNTIME_DIR\" DBUS_SESSION_BUS_ADDRESS=\"$DBUS_ADDR\" systemctl --user enable --now switchdeckd.service" || true
        fi
    else
        HOME="$DECK_HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$RUNTIME_DIR}" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-$DBUS_ADDR}" systemctl --user daemon-reload && \
        HOME="$DECK_HOME" XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$RUNTIME_DIR}" DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-$DBUS_ADDR}" systemctl --user enable --now switchdeckd.service || true
    fi
fi

echo "[SwitchDeck] Installed. Run '${BIN_DIR}/switchdeckctl doctor' to verify hardware!"
