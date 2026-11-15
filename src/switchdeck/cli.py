"""Command-line interface (`switchdeckctl`) including local simulation demo."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
from pathlib import Path
from typing import Any

from .backends import LinuxHardwareBackend, MockHardwareBackend
from .coordinator import SwitchDeckCoordinator
from .daemon import default_socket_path
from .domain import DeckModel, GameWindowState
from .profiles import ProfileStore
from .security import validate_host, validate_port
from .tv import SamsungTizenDriver


def _send_ipc(cmd: str, socket_path: Path) -> dict[str, Any] | None:
    if not socket_path.exists():
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.5)
            sock.connect(str(socket_path))
            sock.sendall((json.dumps({"cmd": cmd}) + "\n").encode("utf-8"))
            data = sock.recv(65536)
            return json.loads(data.decode("utf-8"))
    except (OSError, ValueError):
        return None


def _run_doctor() -> int:
    backend = LinuxHardwareBackend()
    coord = SwitchDeckCoordinator(backend)
    status = coord.reconcile()
    print(f"Deck Model        : {status.deck_model.value}")
    print(f"Docked            : {status.is_docked} (connector={status.active_connector}, ac={status.ac_online})")
    print(
        f"APU Temp / SMU Max: "
        f"{f'{status.apu_temp_c:.1f}C' if status.apu_temp_c is not None else 'n/a'} / {status.hw_max_tdp_watts}W"
    )
    if status.overclock_active or status.overclock_status_note:
        print(f"Docked Overclock  : active={status.overclock_active} ({status.overclock_status_note or 'idle'})")
    print(f"Active EDID       : {status.active_edid_id}")
    print(f"Selected Output   : {status.selected_output_mode.label if status.selected_output_mode else 'handheld'}")
    print(f"Built-in 28de:1205: {'BOUND (active)' if status.builtin_controller_bound else 'UNBOUND (external P1)'}")
    print(f"Active Gamepads   : {len(status.active_controllers)}")
    for c in status.active_controllers:
        print(f"  + {c.name} [{c.usb_id}] via {c.transport}")
    print(f"Sleeping Dongles  : {len(status.sleeping_controllers)}")
    for c in status.sleeping_controllers:
        print(f"  - {c.name} [{c.usb_id}] via {c.transport} (waiting for wake input)")
    if status.unhandled_dongles:
        print("WARNINGS:")
        for w in status.unhandled_dongles:
            print(f"  ! [{w.usb_id}] {w.device_name}: {w.remediation}")
        return 2
    return 0


def _run_demo() -> int:
    """Simulate LCD (Jupiter) + USB-C Hub + 2.4GHz Xbox Dongle + Samsung S90C OLED."""
    with tempfile.TemporaryDirectory() as tmp:
        store = ProfileStore(Path(tmp))
        mock = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD)
        mock.active_game = GameWindowState(
            pid=4242, app_id=99001, window_id=101, server_idx=1,
            width=1280, height=800, gpu_busy_percent=62, title="Zelda64Recompiled",
        )
        coord = SwitchDeckCoordinator(mock, store=store)

        print("== 1. Handheld Baseline ==")
        s1 = coord.reconcile()
        print(f"  docked={s1.is_docked} builtin_bound={s1.builtin_controller_bound} "
              f"vol={mock.volume:.2f} tdp={s1.tdp_watts}W lcd_bt_wake={s1.lcd_bluetooth_wakeup_enabled}")

        print("\n== 2. Drop LCD Deck into USB-C Hub (Samsung S90C + Sleeping 2.4GHz Xbox Dongle) ==")
        mock.attach_samsung_s90c_hub(include_24g_xbox_dongle=True, pad_awake=False)
        s2 = coord.reconcile()
        print(f"  edid={s2.active_edid_id} mode={s2.selected_output_mode.label if s2.selected_output_mode else None}")
        print(f"  builtin_bound={s2.builtin_controller_bound} (kept bound until Xbox pad wakes!)")
        print(f"  charge_limit={s2.charge_limit}% tdp={s2.tdp_watts}W lcd_bt_wake={s2.lcd_bluetooth_wakeup_enabled}")
        print(f"  audio={s2.audio_sink} vol={mock.volume:.2f}")
        print(f"  scaling={s2.last_scaling.target_width}x{s2.last_scaling.target_height} "
              f"{s2.last_scaling.scaling_filter.name} ({s2.last_scaling.reason})")

        print("\n== 3. Press Xbox Guide Button (2.4GHz Pad Wakes) & Recomp Resizes to 1080p ==")
        mock.wake_wireless_controller()
        mock.active_game = GameWindowState(
            pid=4242, app_id=99001, window_id=101, server_idx=1,
            width=1920, height=1080, gpu_busy_percent=68, title="Zelda64Recompiled",
        )
        s3 = coord.reconcile()
        print(f"  builtin_bound={s3.builtin_controller_bound} (Xbox pad promoted to P1!)")
        print(f"  scaling={s3.last_scaling.target_width}x{s3.last_scaling.target_height} "
              f"{s3.last_scaling.scaling_filter.name} ({s3.last_scaling.reason})")

        print("\n== 4. Unplug Hub Mid-Game While Xbox Pad Still Powered On ==")
        mock.detach_hub(keep_wireless_controller=True)
        mock.active_game = GameWindowState(
            pid=4242, app_id=99001, window_id=101, server_idx=1,
            width=1280, height=800, gpu_busy_percent=58, title="Zelda64Recompiled",
        )
        s4 = coord.reconcile()
        print(f"  docked={s4.is_docked} builtin_bound={s4.builtin_controller_bound} "
              f"lcd_bt_wake={s4.lcd_bluetooth_wakeup_enabled} vol={mock.volume:.2f}")
        print("  events_log:")
        for entry in mock.events_log:
            print(f"    * {entry}")
        coord.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="switchdeckctl", description="Control & inspect SwitchDeck")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="Show current SwitchDeck status JSON")
    sub.add_parser("doctor", help="Inspect Deck hardware, controllers & Xbox 2.4GHz dongle status")
    sub.add_parser("charge-full", help="Override 80% dock cap to charge to 100% before travel")
    sub.add_parser("rebind-builtin", help="Emergency rebind of Steam Deck built-in controls")
    sub.add_parser("nudge-display", help="Pulse GAMESCOPE_DISPLAY_MODE_NUDGE to recover blank HDMI")
    sub.add_parser("demo", help="Run interactive local simulation (no Steam Deck required)")

    pair_p = sub.add_parser("pair-samsung", help="Pair & configure Samsung Tizen TV (e.g. S90C)")
    pair_p.add_argument("host", help="Samsung TV LAN IP address")
    pair_p.add_argument("--mac", default="", help="Optional TV MAC address for Wake-on-LAN")
    pair_p.add_argument("--port", type=int, default=8002)
    pair_p.add_argument("--profile", default="default", help="EDID profile ID (or 'default')")
    pair_p.add_argument(
        "--trust-new-cert",
        action="store_true",
        help="Accept and re-pin a changed Samsung TV TLS certificate fingerprint",
    )

    args = parser.parse_args(argv)
    sock_path = default_socket_path()

    if args.command == "demo":
        return _run_demo()
    if args.command == "doctor":
        return _run_doctor()
    if args.command == "pair-samsung":
        try:
            host = validate_host(args.host)
            port = validate_port(args.port)
            store = ProfileStore()
            if args.trust_new_cert:
                store.clear_cert_fingerprint(host)
            driver = SamsungTizenDriver(
                get_token=store.get_token,
                set_token=store.set_token,
                get_cert_fingerprint=store.get_cert_fingerprint,
                set_cert_fingerprint=store.set_cert_fingerprint,
            )
            token = driver.pair(host, port=port, trust_new_cert=args.trust_new_cert)
            prof = store.get_profile(args.profile)
            prof.tv.driver = "samsung_tizen"
            prof.tv.host = host
            prof.tv.port = port
            if args.mac:
                prof.tv.mac_address = args.mac
            store.put_profile(prof)
            print(f"Paired Samsung TV {host} (token saved={'yes' if token else 'pending'}).")
            return 0
        except (ValueError, OSError) as exc:
            print(f"Failed to pair Samsung TV: {exc}", file=sys.stderr)
            return 1

    ipc_map = {
        "status": "status",
        "charge-full": "charge_full",
        "rebind-builtin": "rebind_builtin",
        "nudge-display": "nudge_display",
    }
    resp = _send_ipc(ipc_map[args.command], sock_path)
    if resp is None:
        if args.command == "rebind-builtin":
            ok = LinuxHardwareBackend().set_builtin_controller_bound(True)
            print(json.dumps({"ok": ok, "fallback": "direct_rebind"}))
            return 0 if ok else 1
        print(json.dumps({"ok": False, "error": f"switchdeckd not running at {sock_path}"}))
        return 1

    print(json.dumps(resp, indent=2))
    return 0 if resp.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
