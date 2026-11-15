# SwitchDeck: Primary-Source Research & Engineering Action Plan

> **Goal:** Turn a Steam Deck (LCD `Jupiter` or OLED `Galileo`) into a true Nintendo Switch / Switch 2–class hybrid console when docked—without disabling SteamOS's read-only root filesystem, breaking OS updates, or leaving handheld controls stranded.

---

## 1. Executive Vision: Closing the 7 "Switch vs. Steam Deck" Docking Gaps

When you drop a Nintendo Switch or Switch 2 into its dock, seven distinct system transitions happen atomically within roughly a second. Stock SteamOS 3.6/3.7+ handles pieces of this, yet real-world docking still breaks immersion in predictable ways:

| # | Transition Moment | Nintendo Switch / Switch 2 Behavior | Stock SteamOS / Legacy Workarounds | SwitchDeck Target Behavior |
|---|---|---|---|---|
| 1 | **Controller P1 Handoff** | Handheld Joy-Cons detach/sleep; wireless Pro Controller instantly becomes Player 1. Undocking immediately restores handheld controls. | Built-in Neptune (`28de:1205`) stays Player 1 unless manually reordered per game. Legacy udev scripts unbind controls even on fake mouse/keyboard joystick nodes, or leave Deck buttons dead after undocking while Bluetooth is still on. | **Dock-gated smart P1 handoff:** unbinds `28de:1205` *only when docked AND a real external gamepad is active*; rebinds in `<50 ms` on undock regardless of Bluetooth state, with crash-safe watchdog recovery. |
| 2 | **Live Resolution & Aspect Ratio** | Game transitions seamlessly between handheld (720p/1080p) and docked (1080p–4K) render & UI targets. | Games launched handheld stay stuck at `1280x800` (16:10) when docked mid-session, or require quitting and tweaking Steam's per-game `Game Resolution` override. | **Pre-launch + live mid-game scaling:** swaps `SetAppResolutionOverride` automatically AND updates Gamescope's `GAMESCOPE_XWAYLAND_MODE_CONTROL` + FSR atoms live—resizing SDL2/RT64 recompilations (*Ocarina of Time*, *Majora's Mask*) from 16:10 to 16:9 widescreen without restarting. |
| 3 | **TV Wake & Input Switching** | TV powers on and jumps straight to the Switch HDMI input via CEC. | Native HDMI-CEC (`HdmiCec1` / `cecd`) works mainly on the Official Valve Dock; third-party USB-C hubs (\$20–\$40) lack DP-to-HDMI CEC wiring. | **Dual-path TV control:** drives `steamos-manager` `HdmiCec1` / `/dev/cec*` when supported, plus a **Wi-Fi Smart TV Bridge** (LG WebOS, Roku ECP, Android TV / Sony Bravia, Home Assistant) so any dock switches TV power & HDMI input. |
| 4 | **Couch Wake via Controller** | Press Home on a wireless controller from the couch to wake both console and TV. | OLED (`Galileo`) supports Bluetooth wake; LCD (`Jupiter`) disables it by default due to accidental case-wakes and overheating. | **Model-aware wake gating:** on `Jupiter` (LCD), enables USB/BT `power/wakeup` *only while docked* and clears it immediately on undock—safe couch wake with zero case-overheat risk. |
| 5 | **Power, Fan & Battery Longevity** | Clocks ramp up seamlessly on AC power; console stays safe living in the dock. | Manual QAM TDP/GPU slider juggling; leaving a Deck docked at 100% degrades battery health unless manually capped. | **Automated `steamos-manager` profiles:** handheld `7–11 W` efficiency vs. docked `15 W` unlocked clocks + automatic `80%` `BatteryChargeLimit1` while docked with a 1-tap *"Going Portable: Charge to 100%"* QAM button. |
| 6 | **Audio Routing & Volume Safety** | Audio shifts cleanly to HDMI (or stays on connected wireless headphones) with separate docked/handheld volumes. | AMD VanGogh (`acp5x`) / HDMI PipeWire nodes suspend on idle or blast TV/speakers at the wrong volume level. | **WirePlumber profile router:** disables VanGogh idle suspend, preserves active Bluetooth headphones on dock, and remembers separate Handheld vs. Per-Dock volume levels. |
| 7 | **Mid-Game Undock Safety & Polish** | Iconic *"Click-Clack"* overlay & chime; picking up the console mid-cutscene never misses a beat. | Silent, stuttery black screen during DRM modeset while the game keeps running blindly. | **Switch-style HUD toast + optional Auto-Pause (`SIGSTOP`):** pauses the active game PID during unexpected mid-game undock and shows *"Handheld Ready — Press A to Resume"* (`SIGCONT`). |

---

## 2. Existing Ecosystem Audit & Why Current Scripts Fall Short

Before building `SwitchDeck`, we audited the primary community tools and SteamOS components already solving slices of this problem:

1. **Stock SteamOS 3.6 / 3.7+ (`steamos-manager` + `gamescope`)**
   - *What it already gives us:* Official D-Bus APIs (`com.steampowered.SteamOSManager1`) for TDP (`TdpLimit1`), GPU clocks (`GpuPerformanceLevel1`), battery charge caps (`BatteryChargeLimit1`), and HDMI-CEC (`HdmiCec1` toggling `plasma-remotecontrollers.service` and `wakehook.service`), plus runtime X11 control atoms in Gamescope.
   - *Where it stops short:* It does not automatically switch per-game resolution profiles, reorder/unbind the built-in Neptune gamepad, remember per-dock volumes/EDIDs, gate Bluetooth wake on LCD Decks, or bridge Wi-Fi Smart TVs for non-CEC docks.

2. **`nateify/SteamDeck-Builtin-Disabler` & `scawp/Steam-Deck.Auto-Disable-Steam-Controller`**
   - *What they do well:* Proven `usbhid` unbinding of Valve's internal controller (`28de:1205`, interfaces `3-3:1.0`, `3-3:1.1`, `3-3:1.2` in `sdbd.py`), with `nateify`'s Python rewrite even detecting Valve's Steam Controller 2 Puck (`28de:1304` / `1305`) via hidraw streaming checks.
   - *Critical design gaps:*
     - **No dock awareness:** Triggers purely on joystick add/remove. If you pull the Deck out of the dock while a Bluetooth controller is still powered on in the living room, your Deck's built-in controls stay dead!
     - **False-positive input nodes:** Any device flagged `ID_INPUT_JOYSTICK=1` (some Logitech/Razer wireless receiver dongles, foot pedals, or virtual axes) can trigger an unbind even in handheld mode.
     - **Root filesystem footprint:** `install.sh` writes to `/etc/udev/rules.d/99-disable-steam-input.rules`, `/etc/atomic-update.conf.d/sdbd.conf`, and `/root/.local/bin/sdbd.py`, requiring `root` filesystem changes.
     - **Hardcoded USB topology:** `sdbd.py` hardcodes `STEAM_DECK_USB_PATHS = ["3-3:1.0", "3-3:1.1", "3-3:1.2"]` instead of discovering `28de:1205` interfaces dynamically in `/sys/bus/usb/devices/`.

3. **`tomsch/decky-display-switcher`, `datbird/Docky`, `shaka456/custom-resolution`, `PowerTools`, `PauseGames`**
   - *What they prove:* Decky Loader plugins running under `PluginLoader` (`User=root`) survive SteamOS A/B updates cleanly under `~/homebrew/`, can call `window.SteamClient.Apps.SetAppResolutionOverride(appid, res)` inside SteamCEF (`shaka456/custom-resolution`), and can safely pause/resume foreground game processes.
   - *Critical gap:* Fragmented UX. Stitching five separate plugins and shell scripts together produces race conditions during dock hotplug (e.g., audio switching before DRM stabilizes, or resolution switching racing against game launch).

---

## 3. Recommended Architecture: Standalone-First Universal Daemon + Optional Decky Adapter (`SwitchDeck`)

To guarantee universal compatibility across any Steam Deck (LCD `Jupiter` or OLED `Galileo`), any USB-C hub or dock, and any SteamOS / Linux handheld configuration—with or without Decky Loader installed—`SwitchDeck` uses a **Standalone-First User-Session Daemon (`switchdeckd`)** written in **100% zero-dependency Python 3 stdlib**, paired with a tiny validated root sysfs helper (`switchdeck-helper`) and a Unix domain socket IPC (`/run/user/<uid>/switchdeck.sock`) that `switchdeckctl` or an optional Phase 4 Decky UI plugin can attach to.

```text
switchdeck-dock-daemon/
├── pyproject.toml                         # Zero external deps (Python 3.11+ stdlib only)
├── src/switchdeck/
│   ├── domain.py                          # Hardware/display/scaling/profile dataclasses & enums
│   ├── edid.py                            # 128-byte EDID parser + HDMI 2.0/2.1 Mode Scorer
│   ├── scaling.py                         # Universal "Whatever Config" geometry + GPU scaling engine
│   ├── tv.py                              # Samsung Tizen WSS (:8002) + WoL, HDMI-CEC, Roku, WebOS/Webhook
│   ├── coordinator.py                     # Deterministic Dock/Undock, P1 Handoff & Failsafe state machine
│   ├── daemon.py                          # asyncio AF_NETLINK uevent listener + Unix Socket JSON-RPC
│   ├── cli.py                             # switchdeckctl (status, doctor, charge-full, pair-samsung, demo)
│   └── backends/
│       ├── protocol.py                    # HardwareBackend Protocol
│       ├── linux.py                       # sysfs, evdev capability bits, wpctl, xprop, xwininfo, steamosctl
│       └── mock.py                        # Full macOS/CI hardware simulator (USB-C hub + 2.4GHz + S90C)
├── scripts/
│   ├── switchdeck-helper                  # Root helper (only 28de:1205 usbhid bind/unbind & USB wakeup)
│   ├── install.sh                         # User systemd service + /etc/atomic-update.conf.d/switchdeck.conf
│   ├── uninstall.sh                       # Clean uninstallation + guaranteed 28de:1205 rebind
│   └── deploy_deck.sh                     # 1-command rsync + service restart from macOS to Steam Deck
└── tests/
    └── test_switchdeck.py                 # Stdlib unittest suite covering all hardware scenarios
```

### Key Architectural Pillars

1. **Zero-Dependency Portability & SteamOS Atomic-Update Survival**
   - `switchdeckd` runs as a normal user service (`~/.config/systemd/user/switchdeckd.service`) using Python 3 stdlib + stock SteamOS utilities (`xprop`, `xwininfo`, `wpctl`, `steamosctl`/`busctl`). No `pip`, no `steamos-readonly disable`, and no fragile `/etc/udev/rules.d` rules.
   - Root writes are isolated strictly to `/usr/local/bin/switchdeck-helper` (with a tight sudoers rule validating exact `28de:1205` `usbhid/{bind,unbind}` and USB `power/wakeup` sysfs paths only), preserved across SteamOS A/B updates via `/etc/atomic-update.conf.d/switchdeck.conf`.

2. **Sub-5ms Pure-Python `NETLINK_KOBJECT_UEVENT` Engine + Active Observer Loop**
   - `daemon.py` opens `socket.AF_NETLINK` (`NETLINK_KOBJECT_UEVENT = 15`) inside Python `asyncio` (`loop.add_reader`), waking in `<5 ms` on `drm`, `usb`, `input`, and `power_supply` kernel events with `150 ms` debounce settling.
   - A lightweight `1.5 s` observer checks game window geometry (`xwininfo`), AMD `gpu_busy_percent`, and dormant 2.4GHz USB dongle wake transitions.

3. **Unix Socket JSON-RPC Bridge (`switchdeckctl` & Optional Phase 4 Decky UI)**
   - Both the CLI (`switchdeckctl`) and a future thin Decky QAM plugin communicate over `/run/user/<uid>/switchdeck.sock` (`status`, `doctor`, `charge_full`, `rebind_builtin`, `set_profile`). Even if Steam/Decky crashes or Decky isn't installed, the daemon stays 100% functional.

---

## 4. Deep-Dive Subsystem Designs (Verified Primary-Source Interfaces)

### Subsystem A — Deterministic Dock State, EDID Fingerprinting & Mode Scorer

Relying solely on AC power (`power_supply`) mistakes a wall charger for a TV dock; relying solely on DRM display connection can misfire during brief HDMI cable handshakes. `SwitchDeck` fuses kernel signals into a debounced state machine (`HANDHELD` ↔ `DOCKED`):

1. **External DRM Connector & Binary EDID Parser (`edid.py`):**
   - Scans `/sys/class/drm/card*-*/status` (ignoring internal `eDP-*`) and parses raw `/sys/class/drm/<connector>/edid` bytes: 3-char PNP Manufacturer ID (bytes `0x08..0x09`), product code (`0x0A..0x0B`), Detailed Timing #1 native resolution, `0xFC` Monitor Name descriptor (e.g., `"SAMSUNG S90C"`), and an 8-byte SHA-256 profile key.
2. **Smart HDMI Mode Scorer (Avoiding the `4K@30Hz` Budget Hub Trap):**
   - Many generic USB-C hubs without full HDMI 2.1 FRL bandwidth advertise `3840x2160@30Hz` alongside `1920x1080@120Hz` and `2560x1440@60Hz` on TVs like the **Samsung S90C QD-OLED**.
   - `select_best_output_mode()` strictly penalizes `< 50 Hz` modes (`4K@30Hz`), preferring `1920x1080@120Hz` / `2560x1440@120Hz` / `3840x2160@60-120Hz` for crisp, low-latency 60–120 FPS output.
3. **DRM Black-Screen Recovery Watchdog:** If an external connector reports `connected` after wake but Gamescope fails to light up the display, `SwitchDeck` pulses `GAMESCOPE_DISPLAY_MODE_NUDGE` (`32c = 1`) on `DISPLAY=:0`—verified in `ValveSoftware/gamescope/src/steamcompmgr.cpp:7570` (`GetBackend()->DirtyState( true )`).

---

### Subsystem B — Smart "Player 1" Controller Handoff, 2.4GHz Dongle Promotion & `045e:02fe` Diagnostics

To handle Bluetooth pads, wired pads, and always-plugged-in **2.4GHz USB-A wireless dongles** cleanly:

1. **Strict Truth Table for Built-in Controller (`28de:1205`) Unbinding:**
   $$\text{should\_unbind\_builtin} = \text{is\_docked} \land (\text{count(active\_external\_gamepads)} \ge 1) \land \neg \text{manual\_override\_keep\_builtin}$$
   - **Active-Input / Wakeup-Count Promotion for 2.4GHz Dongles:** A USB 2.4GHz receiver stays enumerated on the hub even when your Xbox controller is turned *off*. `LinuxHardwareBackend` checks `/sys/class/input/input*/device/power/wakeup_count` and non-blocking `EV_KEY`/`EV_ABS` activity on `/dev/input/event*` so an idle/sleeping dongle keeps `28de:1205` bound until the wireless controller wakes and sends input.
   - **Instant Undock Recovery:** Pulling the Deck off the USB-C hub (`is_docked == False`) immediately rebinds `28de:1205` in `<50 ms` *even if the wireless controller stays turned on*.

2. **Real-Gamepad Capability Filtering & `045e:02fe` Driver Diagnostics:**
   - Validates gamepads directly from `/sys/class/input/input*/capabilities/{ev,key,abs}` (`EV_KEY` containing `BTN_SOUTH` bit `0x130` **and** `EV_ABS` containing `ABS_X`/`ABS_Y`), rejecting `28de:1205` (Neptune) and `28de:11ff` (Steam Virtual Gamepad) as well as mouse/keyboard receivers that advertise phantom joystick nodes.
   - Supports USB `xpad`, kernel `xone`, user-space `uinput` (`medusalix/xow` / `InputPlumber`), Bluetooth `uhid`, and Valve's Steam Controller 2 Puck (`28de:1304` / `1305`).
   - **Xbox Wireless Adapter Detection (`045e:02fe` / `045e:02e6`):** SteamOS ships without an in-tree `xone` kernel driver for Microsoft's proprietary 2.4GHz Xbox Wireless Adapter. `switchdeckctl doctor` inspects `/sys/bus/usb/devices/*/idVendor:idProduct` and warns immediately with actionable guidance (`dlundqvist/xone` or Bluetooth mode) if a Microsoft adapter is plugged in without an active driver.

3. **Three-Layer Crash Failsafe:**
   - Signal handlers (`SIGTERM`, `SIGINT`), `atexit`, and `coordinator.close()` unconditionally rebind `28de:1205`.
   - `switchdeckctl rebind-builtin` provides a one-line recovery command.

---

### Subsystem C — Universal "Whatever Config They Have" Scaling & Recomp Engine

Instead of maintaining a whitelist of games or forcing manual per-game Steam settings, `scaling.py` handles **every game automatically** by observing its live X11 geometry (`xwininfo`) inside Gamescope and AMD GPU utilization (`gpu_busy_percent`):

#### 1. Verified Gamescope Runtime X11 Atoms (`ValveSoftware/gamescope`)

| X11 Root Property Atom | Format & Verified Payload (`steamcompmgr.cpp`) | Runtime Effect |
|---|---|---|
| `GAMESCOPE_XWAYLAND_MODE_CONTROL` | `32c` — **4 uint32 values**: `[server_idx, width, height, allowSuperRes]` (`steamcompmgr.cpp:7464-7499`) | Dynamically calls `wlserver_set_xwayland_server_mode(server_idx, width, height, g_nOutputRefresh)` to resize the game's XWayland container live (`1280x800` ↔ `1920x1080` / `1600x900` / `1280x720`). Gamescope deletes the atom once applied. |
| `GAMESCOPE_NEW_SCALING_FILTER` | `32c` — `uint32` enum (`main.hpp:40-48`): `0=LINEAR`, `1=NEAREST`, `2=FSR`, `3=NIS`, `4=PIXEL`, `5=SGSR` | Automatically selects `PIXEL` (`<= 540p`), `FSR` (sub-native game window), or `LINEAR` (1:1 native). |
| `GAMESCOPE_NEW_SCALING_SCALER` | `32c` — `uint32` enum (`main.hpp:80-87`): `0=AUTO`, `1=INTEGER`, `2=FIT`, `3=FILL`, `4=STRETCH` | Uses `INTEGER` for low-res pixel art and `FIT` for clean widescreen/pillarbox scaling. |
| `GAMESCOPE_SCALING_FILTER` | `32c` — legacy compat (`0=LINEAR`, `1=NEAREST`, `2=INTEGER`, `3=FSR`, `4=NIS`) | Automatic compatibility fallback alongside `GAMESCOPE_NEW_SCALING_FILTER`. |
| `GAMESCOPE_FSR_SHARPNESS` | `32c` — `uint32` clamped `[0..20]` (`steamcompmgr.cpp:7458-7463`) | Automatically tunes FSR sharpness (`2`) when upscaling. |
| `GAMESCOPE_FPS_LIMIT` | `32c` — `uint32` target FPS (`0` = unlimited) | Optional handheld vs. docked FPS target. |
| `GAMESCOPE_VRR_ENABLED` | `32c` — `uint32` (`0` or `1`) | Enables VRR automatically when `GAMESCOPE_VRRCapable == 1`. |
| `GAMESCOPE_DISPLAY_MODE_NUDGE` | `32c` — `1` (`steamcompmgr.cpp:7570-7574`) | Triggers `GetBackend()->DirtyState(true)` to recover stalled HDMI handshakes on wake. |

#### 2. Universal Rules That Adapt to Any Game Config

1. **SDL2 / RT64 Recompilations (*Zelda64Recomp*, *Ship of Harkinian*, *2Ship2Harkinian*):** Because `Zelda64Recomp` opens `SDL_WINDOW_RESIZABLE | SDL_WINDOW_VULKAN` with `AspectRatio::Expand` and `HUDRatioMode::Clamp16x9` (`src/main/main.cpp:139`, `src/game/config.cpp:26-30`), setting `GAMESCOPE_XWAYLAND_MODE_CONTROL = [server_idx, 1920, 1080, 0]` pushes a live X11 resize into SDL2—expanding 3D gameplay from `1280x800` (16:10) to `1920x1080` (16:9) mid-game. On a 1080p target, it runs crisp `LINEAR`; on a 4K S90C panel, `SwitchDeck` engages `FSR` to sharpen `1080p -> 4K`.
2. **Games Locked to `720p` / `800p` (Proton / Fixed Config):** If the game ignores the `1080p` XWayland resize and keeps a `<= 800p` window, `SwitchDeck` detects `window_height < output_height` and automatically activates `FSR` + `FIT` + `sharpness=2`.
3. **Low-Res Retro (`<= 540p`):** Automatically switches to `PIXEL` + `INTEGER` so 240p/480p sprites stay razor-sharp.
4. **Adaptive GPU Overload Step-Down:** If a heavy 3D game *does* jump to `1080p` and pins `gpu_busy_percent >= 97%` across consecutive samples, `SwitchDeck` automatically steps the XWayland container down (`1920x1080 -> 1600x900 -> 1280x720`) and activates `FSR`—recovering smooth frame pacing without manual menu tweaking.

---

### Subsystem D — Power, Thermals & Battery Longevity (`steamos-manager` D-Bus)

Inspecting `evlaV/steamos-manager` (`data/interfaces/com.steampowered.SteamOSManager1.xml`, `steamosctl.rs:338`) confirmed that `steamosctl` connects to the **user session D-Bus** (`Connection::session()`) at `com.steampowered.SteamOSManager1`, `/com/steampowered/SteamOSManager1`. Because `switchdeckd` itself runs inside the `deck` user session, it calls `steamosctl` / session D-Bus directly without cross-user permission hoops:

| Interface (`com.steampowered.SteamOSManager1.*`) | Properties Used | Dock Transition Action |
|---|---|---|
| `TdpLimit1` | `TdpLimit` (`u`), `TdpLimitMin` (`u`), `TdpLimitMax` (`u`) | Restores per-profile TDP (`7–11 W` handheld -> `15 W` docked). |
| `GpuPerformanceLevel1` | `GpuPerformanceLevel` (`s`: `auto`/`manual`), `ManualGpuClock` (`u`) | Releases manual GPU clock caps (`auto`) when docked on AC power. |
| `BatteryChargeLimit1` | `MaxChargeLevel` (`i`), `SuggestedMinimumLimit` (`i`) | Automatically sets `MaxChargeLevel = 80` while docked (`switchdeckctl charge-full` resets to `-1` / 100% before travel). |

---

### Subsystem E — Couch Wake (LCD `Jupiter` vs. OLED `Galileo`) & Universal TV Control

#### 1. Model-Aware Couch Wake (`Jupiter` vs. `Galileo`)

`SwitchDeck` reads `/sys/devices/virtual/dmi/id/product_name`:
- **`Galileo` (OLED):** Native Bluetooth wake remains active.
- **`Jupiter` (LCD):** Dynamically sets `power/wakeup = enabled` on internal Bluetooth USB nodes and docked 2.4GHz USB dongles **only while `is_docked == True`**, clearing it back to `disabled` immediately on undock—giving your LCD Deck couch wake while eliminating carrying-case overheat risks.

#### 2. Universal TV Control Registry (`tv.py`: CEC + Samsung S90C Tizen WSS + Roku + WebOS/Webhook)

1. **Path 1 — Hardware HDMI-CEC (`CecTvDriver`):** Configures `com.steampowered.SteamOSManager1.HdmiCec1` (`HdmiCecState = 2` `ControlAndWake`, controlling `plasma-remotecontrollers.service` and `wakehook.service`) and dispatches `/dev/cec*` (`cec-ctl --image-view-on` / `--active-source`) on CEC-wired docks.
2. **Path 2 — Samsung S90C / Tizen SmartView WSS (`SamsungTizenDriver`):** Most generic USB-C hubs do not pass DP-Aux CEC pins. Using zero-dependency Python stdlib (`socket` + `ssl` + `hashlib` RFC 6455 WebSocket), `SwitchDeck`:
   - Sends a UDP Wake-on-LAN magic packet (`FF*6 + MAC*16`) to wake a standby S90C,
   - Connects over TLS port `8002` (`wss://<TV-IP>:8002/api/v2/channels/samsung.remote.control?name=...&token=...`) to send `KEY_POWERON` / `KEY_HDMI`,
   - Persists the one-time pairing token returned by `ms.channel.connect` inside `~/.config/switchdeck/tv_tokens.json` (`switchdeckctl pair-samsung <TV-IP> --mac <TV-MAC>`).
3. **Path 3 — Roku ECP, LG WebOS & Home Assistant Webhooks (`RokuEcpDriver`, `WebhookTvDriver`):** Built-in stdlib HTTP/WebSocket drivers cover Roku (`:8060/keypress/PowerOn` + `/InputHDMIx`) and generic smart-home webhooks.

---

### Subsystem F — Bulletproof PipeWire Audio & Mid-Game Undock Auto-Pause

1. **PipeWire / WirePlumber HDMI Reliability (`audio_router.py`):**
   - Writes `~/.config/wireplumber/wireplumber.conf.d/51-switchdeck-keepalive.conf` setting `session.suspend-timeout-seconds = 0` and `node.pause-on-idle = false` for AMD VanGogh (`alsa_output.platform-acp*` / `alsa_output.pci-0000_04_00.5.*`) so HDMI audio never clips after silence.
   - **Smart Routing Rules:** Preserves connected Bluetooth headphones (`bluez_output.*`) when docking; otherwise binds the active HDMI sink (`wpctl set-default`) and maintains independent Handheld vs. Per-EDID Docked volumes (zero 100%-volume speaker surprises).
2. **Optional Mid-Game Undock Auto-Pause (`SIGSTOP` / `SIGCONT`):**
   - When enabled, freezes the active game process (`SIGSTOP`) briefly on mid-game undock while rebinding `28de:1205` and restoring the `1280x800` screen, then resumes cleanly (`SIGCONT`).

---

## 5. Phased Implementation Roadmap & Current Status

| Phase | Target Deliverable | Status | Verification Criteria |
|---|---|---|---|
| **Phase 0** | **Dev Harness & Hardware Simulator** | **Implemented (This Turn)** | `MockHardwareBackend` simulates LCD `Jupiter` + USB-C hub + 2.4GHz dongle + Samsung S90C EDID locally on macOS; `unittest` suite passes `100%`. |
| **Phase 1** | **Core Daemon & P1 Controller + Audio Engine** | **Implemented (This Turn)** | `AF_NETLINK` watcher, EDID parser/scorer, `28de:1205` smart P1 handoff + dongle promotion + `045e:02fe` doctor, PipeWire split-volume router, 3-layer crash failsafe. |
| **Phase 2** | **Universal Scaling & `steamos-manager` Power** | **Implemented (This Turn)** | Universal X11 window + `gpu_busy_percent` adaptive scaler (`FSR`/`PIXEL`/`LINEAR` + overload step-down) & `steamosctl` TDP/`80%` battery cap. |
| **Phase 3** | **LCD/OLED Wake & Universal TV Control** | **Implemented (This Turn)** | Dock-gated LCD `power/wakeup`, `HdmiCec1`, Samsung Tizen WSS `:8002` + WoL, Roku ECP, and Home Assistant webhook drivers. |
| **Phase 4** | **Decky Loader QAM Plugin, Hardening & Visual QA** | **Implemented (`v0.2.0`)** | Full Decky Loader plugin (`plugin.json`, `main.py`, `src/index.tsx` + `src/ui/**`), Switch Click-Clack HUD toast/chime, TOFU TLS cert pinning, system hardening, `SwitchDeck-v0.2.0.zip`, and Chrome headless GamepadUI visual verification. |

---

## 6. Verified Primary Sources & Reference Links

All architectural claims, X11 atom layouts, D-Bus signatures, and driver paths above were verified directly against their canonical upstream repositories:

1. **Valve Gamescope (X11 Atoms, Scaling Enums & Runtime Mode Control)**
   - [`ValveSoftware/gamescope` — `src/xwayland_ctx.hpp`](https://raw.githubusercontent.com/ValveSoftware/gamescope/master/src/xwayland_ctx.hpp) — Root atom declarations (`gamescopeXWaylandModeControl`, `gamescopeNewScalingFilter`, `gamescopeNewScalingScaler`, `gamescopeDisplayModeNudge`, `gamescopeVRREnabled`).
   - [`ValveSoftware/gamescope` — `src/steamcompmgr.cpp`](https://raw.githubusercontent.com/ValveSoftware/gamescope/master/src/steamcompmgr.cpp) — Atom handlers (`GAMESCOPE_XWAYLAND_MODE_CONTROL` 4-uint32 format at lines 7464–7499; `GAMESCOPE_SCALING_FILTER` at 7429–7457; `GAMESCOPE_FSR_SHARPNESS` at 7458–7463; `GAMESCOPE_DISPLAY_MODE_NUDGE` at 7570–7574).
   - [`ValveSoftware/gamescope` — `src/main.hpp`](https://raw.githubusercontent.com/ValveSoftware/gamescope/master/src/main.hpp) — `GamescopeUpscaleFilter` and `GamescopeUpscaleScaler` enum definitions (lines 40–87).
2. **Valve SteamOS Manager (`steamos-manager` D-Bus API & CEC Control)**
   - [`evlaV/steamos-manager` — `data/interfaces/com.steampowered.SteamOSManager1.xml`](https://gitlab.com/evlaV/steamos-manager/-/raw/master/data/interfaces/com.steampowered.SteamOSManager1.xml) — D-Bus introspection spec for `TdpLimit1`, `GpuPerformanceLevel1`, `BatteryChargeLimit1`, and `HdmiCec1`.
   - [`evlaV/steamos-manager` — `steamos-manager/src/cec.rs`](https://gitlab.com/evlaV/steamos-manager/-/raw/master/steamos-manager/src/cec.rs) — `HdmiCecState` (`Disabled`, `ControlOnly`, `ControlAndWake`) controlling `plasma-remotecontrollers.service` and `wakehook.service`.
   - [`evlaV/steamos-manager` — `steamos-manager/src/bin/steamosctl.rs`](https://gitlab.com/evlaV/steamos-manager/-/raw/master/steamos-manager/src/bin/steamosctl.rs) — Session D-Bus connection (`Connection::session()`, line 338) and official subcommands.
3. **Decky Loader & SteamCEF Bridge (Optional Phase 4 UI)**
   - [`SteamDeckHomebrew/decky-loader` — `dist/plugin_loader-release.service`](https://raw.githubusercontent.com/SteamDeckHomebrew/decky-loader/main/dist/plugin_loader-release.service) — Systemd unit (`User=root`, `HOMEBREW_FOLDER`).
   - [`SteamDeckHomebrew/decky-plugin-template` — `main.py`](https://raw.githubusercontent.com/SteamDeckHomebrew/decky-plugin-template/main/main.py) & [`src/index.tsx`](https://raw.githubusercontent.com/SteamDeckHomebrew/decky-plugin-template/main/src/index.tsx) — Modern `import decky` backend & `@decky/api` / `@decky/ui` frontend bridge.
   - [`shaka456/custom-resolution` — `src/api.ts`](https://raw.githubusercontent.com/shaka456/custom-resolution/main/src/api.ts) — Verified `window.SteamClient.Apps.SetAppResolutionOverride` and `GetResolutionOverrideForApp` usage inside SteamCEF.
4. **Neptune Built-in Controller (`28de:1205`), 2.4GHz Xbox Adapters & Community Ecosystem**
   - [`nateify/SteamDeck-Builtin-Disabler` — `sdbd.py`](https://raw.githubusercontent.com/nateify/SteamDeck-Builtin-Disabler/main/sdbd.py) — Valve Neptune USB IDs (`28de:1205`), Steam Controller 2 Puck (`28de:1304`/`1305`), and `usbhid` `bind`/`unbind` mechanics.
   - [`dlundqvist/xone`](https://github.com/dlundqvist/xone) & [`medusalix/xow`](https://github.com/medusalix/xow) — Linux kernel and `uinput` drivers for the official Microsoft 2.4GHz Xbox Wireless Adapter (`045e:02fe` / `045e:02e6`).
   - [`scawp/Steam-Deck.Auto-Disable-Steam-Controller`](https://github.com/scawp/Steam-Deck.Auto-Disable-Steam-Controller), [`tomsch/decky-display-switcher`](https://github.com/tomsch/decky-display-switcher), & [`datbird/Docky`](https://github.com/datbird/Docky).
5. **Smart TV Control & Recompilations**
   - [`xchwarze/samsung-tv-ws-api`](https://github.com/xchwarze/samsung-tv-ws-api) — Samsung Tizen SmartView TLS WebSocket (`wss://<TV>:8002`) token pairing and `KEY_HDMI`/`KEY_POWERON` specification.
   - [`Zelda64Recomp/Zelda64Recomp` — `src/main/main.cpp`](https://raw.githubusercontent.com/Zelda64Recomp/Zelda64Recomp/dev/src/main/main.cpp) & [`src/game/config.cpp`](https://raw.githubusercontent.com/Zelda64Recomp/Zelda64Recomp/dev/src/game/config.cpp) — `SDL_WINDOW_RESIZABLE | SDL_WINDOW_VULKAN`, Steam Deck fullscreen auto-detection, `AspectRatio::Expand`, `HUDRatioMode::Clamp16x9`.
   - [`HarbourMasters/Shipwright`](https://github.com/HarbourMasters/Shipwright) (*Ship of Harkinian* — OoT PC Port) & [`2ship2harkinian/2ship2harkinian`](https://github.com/2ship2harkinian/2ship2harkinian) (*2Ship2Harkinian* — MM PC Port).

---

## 7. v0.2.0 Hardening & Decky Packaging Addendum

SwitchDeck `v0.2.0` hardens every privileged, network, IPC, and process boundary while packaging the full daemon + Switch-style QAM UI into a single Decky Loader ZIP (`dist-zip/SwitchDeck-v0.2.0.zip`):

- **Security & Session Isolation (`security.py`, `session.py`, `scripts/switchdeck-helper`, `scripts/install.sh`):**
  - Root sysfs writes require `validate_neptune_iface` (`28de:1205` USB ID verification) or `validate_wakeup_path` (`os.path.realpath` confined under `/sys/devices/.../power/wakeup`) using `safe_write_sysfs` (`O_WRONLY | O_NOFOLLOW | O_CLOEXEC`). `install.sh` validates `DECK_USER` and checks sudoers drop-ins via `visudo -cf` before placement.
  - `UserSessionContext` (`resolve_user_session`) resolves `DECKY_USER` / `SUDO_USER` / `uid 1000` and drops root privileges when invoking `wpctl`, `xrandr`, `xprop`, `xwininfo`, and `steamosctl` against the active session's `XDG_RUNTIME_DIR`, D-Bus bus, and `XAUTHORITY`.
  - `atomic_write_json` writes profiles/tokens (`0600`) with `0700` parents, `fsync`, optional `chown`, and `os.replace`.
- **Network, TLS TOFU, IPC & Process Safety (`tv.py`, `domain.py`, `profiles.py`, `coordinator.py`, `daemon.py`, `backends/linux.py`):**
  - Samsung Tizen WSS (`:8002`) performs **TOFU SHA-256 certificate pinning** (`ssl.SSLCertVerificationError` on mismatch, explicit rotation via `--trust-new-cert` / QAM re-pair), handles WebSocket `Ping -> Pong`, enforces `16 KiB` handshake and `64 KiB` payload limits, and integrates CRLF/host/port/HDMI/SSRF validators.
  - `DockProfile.from_dict` clamps all numeric fields; `SwitchDeckCoordinator` wraps all state transitions in `RLock` and guarantees undock `SIGCONT` in `try ... finally` with PID `starttime` verification (`validate_game_pid`); `LinuxHardwareBackend` monitors sleeping 2.4GHz dongles via persistent non-blocking `select.poll()` (`POLLIN`) descriptors closed on `close()`, and skips `scope=="Device"` controller batteries in `is_ac_online`.
  - `SwitchDeckDaemon` uses `asyncio.Lock` + `asyncio.to_thread`, `SO_RCVBUF = 262144` netlink sockets, and `0600` symlink-safe Unix IPC sockets (`8 KiB` request cap).
- **Decky Loader Plugin & Packaging (`plugin.json`, `main.py`, `src/index.tsx`, `src/ui/**`, `scripts/build_decky_zip.sh`):**
  - Packages `SwitchDeck/plugin.json` (`"flags": ["root"]`), `SwitchDeck/main.py` (embedded `AF_NETLINK` + 1.5s observer loop, `switchdeck_transition` event emitter, unconditional `28de:1205` rebind in `_unload()`/`_uninstall()`), `SwitchDeck/dist/index.js` (Rollup + `@decky/ui`/`@decky/api` React UI + Switch Click-Clack HUD toast/WebAudio chime), and `SwitchDeck/py_modules/switchdeck/` (stripped of `__pycache__`/`*.pyc`) into `dist-zip/SwitchDeck-v0.2.0.zip`.
  - Visually verified across 4 offline GamepadUI preview scenarios (`handheld_1280x800`, `docked_s90c_1920x1080`, `docked_warning_1920x1080`, `tv_pairing_1280x800`) and backed by a **30-test** stdlib `unittest` suite.

