# SwitchDeck

**Universal Nintendo Switch–style docking daemon and Decky Loader plugin for Steam Deck (LCD `Jupiter` & OLED `Galileo`) and SteamOS.**

SwitchDeck coordinates controller Player-1 handoffs (`28de:1205` Neptune bind/unbind), live Gamescope resolution/FSR scaling, PipeWire audio routing with split handheld/docked volumes, `steamos-manager` TDP & 80% battery charge caps, LCD dock-gated Bluetooth wake, and universal HDMI-CEC + Wi-Fi Smart TV switching — with **zero external Python runtime dependencies** (`Python 3.10+` stdlib only).

---

## Quick Demo & Tests (macOS / Linux Without a Steam Deck)

Run the simulated LCD `Jupiter` + USB-C hub + sleeping 2.4GHz Xbox dongle + Samsung S90C transition:

```bash
PYTHONPATH=src python3 -m switchdeck.cli demo
```

Run the full automated verification suite (**30 `unittest` cases**):

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Build the Decky frontend, preview bundle, and installable Decky Loader ZIP:

```bash
npm run typecheck && npm run build && npm run preview && ./scripts/build_decky_zip.sh
```

---

## Installing on Your Steam Deck

### Option A — Decky Loader Plugin ZIP (Recommended for Game Mode)

1. Use the direct release URL `https://github.com/topuchi13/SwitchDeck/releases/latest/download/SwitchDeck.zip`, or build `dist-zip/SwitchDeck-v0.2.0.zip` locally via `./scripts/build_decky_zip.sh`.
2. On your Steam Deck in **Game Mode**, open **Settings -> System -> Enable Developer Mode**.
3. Open **Settings -> Developer -> Install Plugin from URL** and paste the release URL above, or choose **Install Plugin from ZIP** and select `SwitchDeck-v0.2.0.zip`.
4. Open the **Quick Access Menu (`•••`) -> Decky -> SwitchDeck**.

The packaged plugin (`plugin.json` with `"flags": ["root"]`, `main.py`, `dist/index.js`, and `py_modules/switchdeck/`) runs an in-process `AF_NETLINK` uevent listener + 1.5s observer loop directly inside Decky Loader, resolves the `deck` user session for PipeWire/Gamescope/`steamosctl`, stores profiles/tokens in `DECKY_PLUGIN_SETTINGS_DIR` (`0600`), and unconditionally rebinds `28de:1205` in `_unload()` / `_uninstall()`.

### Option B — Standalone Systemd Daemon (No Decky Required)

Deploy from macOS/Linux over SSH (`passwd` + `sudo systemctl enable --now sshd` on Deck first):

```bash
./scripts/deploy_deck.sh deck@steamdeck.local
```

Or install directly on Steam Deck:

```bash
bash ./scripts/install.sh
~/.local/bin/switchdeckctl doctor
```

Uninstall cleanly (stops service and restores `28de:1205`):

```bash
bash ./scripts/uninstall.sh
```

---

## Switch Click-Clack HUD Toast & Quick Access Menu (QAM)

- **Switch Click-Clack HUD Toast:** Docking or undocking emits `switchdeck_transition`, playing a synthesized Switch-style rail chime (`src/ui/audioChime.ts`) and displaying a glassmorphism HUD toast (`SwitchToastCard`) summarizing the display, output mode, VRR badge, Player-1 controller, scaling filter, TDP/charge cap, and audio sink.
- **Hero Status & Alerts:** Displays `Deck LCD` / `Deck OLED`, `Docked` / `Handheld` status, output mode (`VRR`/`AC` pills), Player-1 controller state, active scaling, TDP/charge cap, LCD BT Wake lock state, and actionable warnings (such as proprietary `045e:02fe` Xbox adapters missing `xone`/`xow`).
- **Quick Controls & Failsafes:**
  - **Keep Built-in Controls** (resets automatically on undock) & **Emergency Rebind Deck Controls**
  - **Travel Charge 100%** (overrides 80% dock battery cap until undock)
  - **Switch Click-Clack HUD** chime/toast toggle
  - **Sync Native App Resolution** (`SteamClient.Apps.SetAppResolutionOverride`) & **Fix Blank TV / Nudge HDMI** (`GAMESCOPE_DISPLAY_MODE_NUDGE`)
- **Display & Scaling Profile:** Per-EDID Container Target (`1080p`, `1440p`, `720p`), **Adaptive GPU Step-Down** (`>= 97%` GPU busy), **FSR Sharpness** (`0–20`), **Docked TDP** (`3–30W`), **Handheld TDP** (`3–15W`), and **Brief Pause on Undock**.
- **Smart TV Bridge:** Select `HDMI-CEC`, `Samsung Tizen Wi-Fi (S90C)`, `Roku TV (ECP LAN)`, `Webhook`, or `Disabled`, inspect `Paired` / `TOFU Pinned` SHA-256 certificate badges, pair, or test TV wake.

---

## Samsung S90C / Tizen Pairing & TOFU TLS Certificate Pinning

Most budget USB-C hubs do not wire HDMI-CEC. SwitchDeck wakes Samsung Tizen TVs via UDP Wake-on-LAN and controls power/HDMI over TLS WebSocket (`wss://<TV-IP>:8002`):

```bash
switchdeckctl pair-samsung <TV-IP> --mac <TV-MAC>
```

- **Trust On First Use (TOFU):** On first connection/pairing, SwitchDeck computes the TV's X.509 certificate SHA-256 fingerprint and persists it alongside the pairing token in `tv_tokens.json` (`0600` permissions, backwards-compatible with legacy plain-string `tv_tokens.json` entries).
- **Fail-Closed Verification:** Every subsequent connection checks the peer certificate SHA-256 against the pinned fingerprint and rejects mismatches with `ssl.SSLCertVerificationError`.
- **Intentional Rotation:** If your TV rotates its certificate (e.g., firmware update), explicitly re-pin via:
  ```bash
  switchdeckctl pair-samsung <TV-IP> --trust-new-cert
  ```
  or click **Trust New TV Cert & Re-Pair** in the Decky QAM panel.

---

## Hardened Security Architecture

- **Sysfs & Helper Containment (`security.py`, `scripts/switchdeck-helper`):** `validate_neptune_iface` restricts USB bind/unbind strictly to verified `28de:1205` interfaces; `validate_wakeup_path` confines wakeup writes via `os.path.realpath` to `/sys/devices/.../power/wakeup`; writes use `O_WRONLY | O_NOFOLLOW | O_CLOEXEC`. `scripts/install.sh` validates `DECK_USER` and checks the sudoers drop-in with `visudo -cf` prior to installation.
- **Session Privilege Isolation (`session.py`):** `UserSessionContext` / `resolve_user_session` resolves `DECKY_USER` / `SUDO_USER` / `uid 1000` and drops root privileges when executing `wpctl`, `xrandr`, `xprop`, `xwininfo`, and `steamosctl` against the user's `XDG_RUNTIME_DIR`, D-Bus bus, and `XAUTHORITY`.
- **Network, Input & IPC Guards (`tv.py`, `domain.py`, `daemon.py`):** Rejects CRLF/header injection and invalid hosts/ports/HDMI inputs, restricts webhooks to `http`/`https` (blocking `file://` SSRF), caps WebSocket handshakes at `16 KiB` and frames at `64 KiB`, handles WebSocket `Ping -> Pong`, clamps all `DockProfile.from_dict` fields, guards `0600` Unix IPC sockets against symlinks with `8 KiB` request caps, and persists JSON atomically (`atomic_write_json`: `0700` parent, `fsync`, `0600`, `os.replace`).
- **Process & Dongle Failsafes (`backends/linux.py`, `coordinator.py`):** Verifies `pid > 100`, non-system `comm`, and `/proc/<pid>/stat` `starttime` before `SIGSTOP`/`SIGCONT`, wraps undock transitions in `try ... finally` to guarantee `SIGCONT` even if scaling fails, monitors sleeping 2.4GHz dongles with persistent non-blocking `os.open` + `select.poll()` (`POLLIN`) descriptors closed on `close()`, and skips `scope=="Device"` controller batteries in `is_ac_online`.

---

## Everyday CLI Commands (`switchdeckctl`)

- `switchdeckctl doctor` — Checks Deck model (`Jupiter` LCD vs `Galileo` OLED), connected external displays/EDID, active gamepads vs dormant 2.4GHz dongles, and warns on unhandled `045e:02fe` / `02e6` Xbox adapters.
- `switchdeckctl status` — Dumps full JSON daemon state.
- `switchdeckctl charge-full` — Temporarily overrides the `80%` docked battery cap to `100%` before travel (resets automatically on undock).
- `switchdeckctl rebind-builtin` — Emergency failsafe immediately restoring the Steam Deck's built-in `28de:1205` controller.
- `switchdeckctl nudge-display` — Pulses `GAMESCOPE_DISPLAY_MODE_NUDGE` to recover a stalled HDMI handshake.
- `switchdeckctl pair-samsung <TV-IP> [--mac <TV-MAC>] [--trust-new-cert]` — Pairs and TOFU-pins a Samsung Tizen TV over WSS `:8002`.
- `switchdeckctl demo` — Runs the full in-memory simulation locally.

## License

Licensed under the BSD 3-Clause License — see [LICENSE](LICENSE).
