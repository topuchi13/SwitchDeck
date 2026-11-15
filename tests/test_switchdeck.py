"""Comprehensive stdlib unittest suite for SwitchDeck (runs locally on macOS/Linux)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import json
import logging
import os
import pwd
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from switchdeck.backends.linux import (
    ABS_X_BIT,
    ABS_Y_BIT,
    BTN_SOUTH_BIT,
    LinuxHardwareBackend,
    _has_cap_bit,
    _parse_cap_words,
)
from switchdeck.backends.mock import MockHardwareBackend
from switchdeck.cli import main as cli_main
from switchdeck.coordinator import SwitchDeckCoordinator
from switchdeck.daemon import SwitchDeckDaemon
from switchdeck.domain import (
    AudioSink,
    DeckModel,
    DisplayMode,
    DockProfile,
    ExternalController,
    GameWindowState,
    GamescopeFilter,
    GamescopeScaler,
    UnhandledDongleWarning,
)
from switchdeck.edid import make_synthetic_edid, parse_edid, select_best_output_mode
from switchdeck.profiles import ProfileStore, default_config_dir
from switchdeck.scaling import compute_universal_scaling
from switchdeck.security import (
    atomic_write_json,
    capture_process_starttime,
    safe_write_sysfs,
    validate_game_pid,
    validate_hdmi_input,
    validate_host,
    validate_neptune_iface,
    validate_port,
    validate_wakeup_path,
    validate_webhook_url,
)
from switchdeck.session import resolve_user_session
from switchdeck.tv import SamsungTizenDriver, WS_GUID, _WsPayloadTooLarge


def _encode_unmasked_ws_frame(text: str) -> bytes:
    data = text.encode("utf-8")
    assert len(data) < 126
    return bytes([0x81, len(data)]) + data


class TestEdidAndModeScoring(unittest.TestCase):
    def test_parse_synthetic_samsung_s90c_edid(self) -> None:
        raw = make_synthetic_edid(
            manufacturer_id="SAM",
            product_code=0x7341,
            monitor_name="SAMSUNG S90C",
            native_width=3840,
            native_height=2160,
        )
        info = parse_edid(raw)
        self.assertIsNotNone(info)
        assert info is not None
        self.assertEqual(info.manufacturer_id, "SAM")
        self.assertEqual(info.product_code, 0x7341)
        self.assertEqual(info.monitor_name, "SAMSUNG S90C")
        self.assertEqual(info.native_width, 3840)
        self.assertEqual(info.native_height, 2160)
        self.assertTrue(info.profile_id.startswith("SAM_SAMSUNG_S90C_"))

    def test_rejects_4k30_hub_trap_for_smooth_modes(self) -> None:
        # Budget USB-C hub only exposing 4K@30Hz alongside 1080p@120Hz and 1440p@60Hz
        modes = [
            DisplayMode(3840, 2160, 30.0, preferred=True),
            DisplayMode(2560, 1440, 60.0, preferred=False),
            DisplayMode(1920, 1080, 120.0, preferred=False),
        ]
        best = select_best_output_mode(modes)
        self.assertIsNotNone(best)
        assert best is not None
        self.assertGreaterEqual(best.refresh_hz, 50.0)
        self.assertEqual((best.width, best.height), (1920, 1080))
        self.assertEqual(best.refresh_hz, 120.0)


class TestCapabilityBitmasks(unittest.TestCase):
    def test_gamepad_vs_mouse_receiver_filtering(self) -> None:
        # Construct sysfs capability bitmasks matching a real Xbox gamepad:
        # BTN_SOUTH (0x130) + ABS_X (0x00) + ABS_Y (0x01)
        gamepad_key_val = 1 << BTN_SOUTH_BIT
        # Format into 64-bit hex words (MSB first, space separated)
        words = []
        v = gamepad_key_val
        while v:
            words.append(f"{v & ((1 << 64) - 1):x}")
            v >>= 64
        words.reverse()
        key_raw = " ".join(words)
        abs_raw = f"{(1 << ABS_X_BIT) | (1 << ABS_Y_BIT):x}"

        key_words = _parse_cap_words(key_raw)
        abs_words = _parse_cap_words(abs_raw)
        self.assertTrue(_has_cap_bit(key_words, BTN_SOUTH_BIT))
        self.assertTrue(_has_cap_bit(abs_words, ABS_X_BIT))
        self.assertTrue(_has_cap_bit(abs_words, ABS_Y_BIT))

        # Mouse/keyboard receiver: BTN_LEFT (0x110) only, no BTN_SOUTH, no ABS_X/Y
        mouse_key_val = 1 << 0x110
        m_words = []
        mv = mouse_key_val
        while mv:
            m_words.append(f"{mv & ((1 << 64) - 1):x}")
            mv >>= 64
        m_words.reverse()
        self.assertFalse(_has_cap_bit(_parse_cap_words(" ".join(m_words)), BTN_SOUTH_BIT))
        self.assertFalse(_has_cap_bit(_parse_cap_words("0"), ABS_X_BIT))


class TestUniversalScalingEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.tmp.name))
        self.profile = self.store.get_profile("test_edid", "Test TV")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_recomp_resizable_1080p_on_1080p_and_4k(self) -> None:
        recomp_1080p = GameWindowState(
            pid=101, app_id=1, window_id=2, server_idx=1,
            width=1920, height=1080, gpu_busy_percent=60, title="Zelda64Recompiled",
        )
        # 1080p TV output -> crisp 1:1 LINEAR
        d_1080 = compute_universal_scaling(
            True, DisplayMode(1920, 1080, 120.0), recomp_1080p, self.profile
        )
        self.assertEqual(d_1080.scaling_filter, GamescopeFilter.LINEAR)
        self.assertEqual((d_1080.target_width, d_1080.target_height), (1920, 1080))

        # 4K S90C output -> 1080p upscaled to 4K automatically uses FSR + FIT
        d_4k = compute_universal_scaling(
            True, DisplayMode(3840, 2160, 60.0), recomp_1080p, self.profile
        )
        self.assertEqual(d_4k.scaling_filter, GamescopeFilter.FSR)
        self.assertEqual(d_4k.scaling_scaler, GamescopeScaler.FIT)

    def test_fixed_aaa_720p_gets_fsr(self) -> None:
        locked_720p = GameWindowState(
            pid=102, app_id=2, window_id=3, server_idx=1,
            width=1280, height=720, gpu_busy_percent=82, title="ProtonAAA",
        )
        dec = compute_universal_scaling(
            True, DisplayMode(1920, 1080, 60.0), locked_720p, self.profile
        )
        self.assertEqual(dec.scaling_filter, GamescopeFilter.FSR)
        self.assertEqual(dec.scaling_scaler, GamescopeScaler.FIT)

    def test_retro_game_gets_pixel_integer(self) -> None:
        retro = GameWindowState(
            pid=103, app_id=3, window_id=4, server_idx=1,
            width=320, height=240, gpu_busy_percent=12, title="SNES",
        )
        dec = compute_universal_scaling(
            True, DisplayMode(3840, 2160, 60.0), retro, self.profile
        )
        self.assertEqual(dec.scaling_filter, GamescopeFilter.PIXEL)
        self.assertEqual(dec.scaling_scaler, GamescopeScaler.INTEGER)

    def test_gpu_overload_steps_down_resolution(self) -> None:
        heavy = GameWindowState(
            pid=104, app_id=4, window_id=5, server_idx=1,
            width=1920, height=1080, gpu_busy_percent=99, title="HeavyGame",
        )
        dec = compute_universal_scaling(
            True, DisplayMode(1920, 1080, 60.0), heavy, self.profile, consecutive_gpu_overload=2
        )
        self.assertEqual((dec.target_width, dec.target_height), (1600, 900))
        self.assertEqual(dec.scaling_filter, GamescopeFilter.FSR)


class TestCoordinatorFlows(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self.tmp.name))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lcd_usb_hub_24g_dongle_and_split_volumes(self) -> None:
        mock = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD, volume=0.35)
        coord = SwitchDeckCoordinator(mock, store=self.store)

        # 1. Handheld baseline
        s0 = coord.reconcile()
        self.assertFalse(s0.is_docked)
        self.assertTrue(s0.builtin_controller_bound)
        self.assertFalse(s0.lcd_bluetooth_wakeup_enabled)
        self.assertTrue(mock.wireplumber_keepalive_written)

        # 2. Dock with sleeping 2.4GHz Xbox dongle -> built-in stays bound until pad wakes!
        mock.attach_samsung_s90c_hub(include_24g_xbox_dongle=True, pad_awake=False)
        s1 = coord.reconcile()
        self.assertTrue(s1.is_docked)
        self.assertTrue(s1.builtin_controller_bound)
        self.assertEqual(len(s1.sleeping_controllers), 1)
        self.assertTrue(s1.lcd_bluetooth_wakeup_enabled)
        self.assertEqual(s1.charge_limit, 80)
        self.assertEqual(s1.tdp_watts, 15)
        self.assertEqual(mock.get_audio_state().default_sink.kind, "hdmi")  # type: ignore[union-attr]
        self.assertAlmostEqual(mock.volume, 0.65)

        # Adjust TV volume to 0.80 while docked
        mock.set_sink_volume(0.80)

        # 3. Wake Xbox 2.4GHz controller -> Neptune unbinds, Xbox is Player 1!
        mock.wake_wireless_controller()
        s2 = coord.reconcile()
        self.assertFalse(s2.builtin_controller_bound)
        self.assertEqual(len(s2.active_controllers), 1)

        # 4. Undock mid-game while 2.4GHz/BT pad is STILL awake -> Deck rebinds immediately,
        # LCD wakeup clears, handheld volume (0.35) restored, game paused/resumed cleanly
        mock.active_game = GameWindowState(
            pid=777, app_id=10, window_id=20, server_idx=1,
            width=1920, height=1080, gpu_busy_percent=65, title="Ship of Harkinian",
        )
        mock.detach_hub(keep_wireless_controller=True)
        s3 = coord.reconcile()
        self.assertFalse(s3.is_docked)
        self.assertTrue(s3.builtin_controller_bound)
        self.assertFalse(s3.lcd_bluetooth_wakeup_enabled)
        self.assertEqual(s3.charge_limit, -1)
        self.assertAlmostEqual(mock.volume, 0.35)
        self.assertNotIn(777, mock.paused_pids)
        self.assertIn("kill:SIGSTOP pid=777", mock.events_log)
        self.assertIn("kill:SIGCONT pid=777", mock.events_log)
        self.assertEqual((s3.last_scaling.target_width, s3.last_scaling.target_height), (1280, 800))  # type: ignore[union-attr]

    def test_bluetooth_headphones_preserved_on_dock(self) -> None:
        mock = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD, volume=0.45)
        mock.sinks = [
            AudioSink(10, "alsa_output.acp5x", "Speaker", "speakers", is_default=False),
            AudioSink(25, "bluez_output.AA_BB", "Sony XM5", "bluetooth", is_default=True),
        ]
        coord = SwitchDeckCoordinator(mock, store=self.store)
        coord.reconcile()

        mock.attach_samsung_s90c_hub(include_24g_xbox_dongle=False)
        coord.reconcile()
        self.assertEqual(mock.get_audio_state().default_sink.kind, "bluetooth")  # type: ignore[union-attr]
        self.assertAlmostEqual(mock.volume, 0.45)

    def test_unhandled_045e_dongle_and_crash_failsafe(self) -> None:
        mock = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD)
        mock.attach_samsung_s90c_hub(include_24g_xbox_dongle=True, pad_awake=True)
        mock.unhandled_dongles = [
            UnhandledDongleWarning(
                usb_id="045e:02fe",
                device_name="Microsoft Xbox Wireless Adapter",
                sysfs_path="/sys/bus/usb/devices/3-1",
                remediation="Install xone or switch to Bluetooth",
            )
        ]
        coord = SwitchDeckCoordinator(mock, store=self.store)
        status = coord.reconcile()
        self.assertFalse(status.builtin_controller_bound)
        self.assertEqual(len(status.unhandled_dongles), 1)
        self.assertEqual(status.unhandled_dongles[0].usb_id, "045e:02fe")

        # Simulate daemon shutdown/SIGTERM while docked -> unconditional rebind + LCD wake off
        coord.close()
        self.assertTrue(mock.is_builtin_controller_bound())
        self.assertFalse(mock.get_lcd_bluetooth_wakeup())


class TestSamsungTizenDriverAndCli(unittest.TestCase):
    def test_samsung_ws_token_capture_and_remote_key(self) -> None:
        tokens: dict[str, str] = {}
        received_commands: list[dict] = []

        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]

        def server_worker() -> None:
            conn, _ = srv.accept()
            with conn:
                req = conn.recv(4096).decode("ascii")
                key_line = [ln for ln in req.splitlines() if ln.lower().startswith("sec-websocket-key:")][0]
                ws_key = key_line.split(":", 1)[1].strip()
                accept = base64.b64encode(hashlib.sha1((ws_key + WS_GUID).encode("ascii")).digest()).decode("ascii")
                conn.sendall(
                    f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                    f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n".encode("ascii")
                )
                # Send Samsung token greeting
                conn.sendall(_encode_unmasked_ws_frame(json.dumps({"event": "ms.channel.connect", "data": {"token": "99887766"}})))
                # Read masked client frame (supports 7-bit and 16-bit RFC 6455 lengths)
                hdr = conn.recv(2)
                plen = hdr[1] & 0x7F
                if plen == 126:
                    plen = struct.unpack("!H", conn.recv(2))[0]
                elif plen == 127:
                    plen = struct.unpack("!Q", conn.recv(8))[0]
                mask = conn.recv(4)
                masked = bytearray()
                while len(masked) < plen:
                    chunk = conn.recv(plen - len(masked))
                    if not chunk:
                        break
                    masked.extend(chunk)
                plain = bytes(b ^ mask[i % 4] for i, b in enumerate(masked)).decode("utf-8")
                received_commands.append(json.loads(plain))

        t = threading.Thread(target=server_worker, daemon=True)
        t.start()

        driver = SamsungTizenDriver(
            get_token=lambda h: tokens.get(h, ""),
            set_token=lambda h, tok: tokens.__setitem__(h, tok),
        )
        tok = driver.send_key("127.0.0.1", port, "KEY_HDMI")
        t.join(timeout=2.0)
        srv.close()

        self.assertEqual(tok, "99887766")
        self.assertEqual(tokens["127.0.0.1"], "99887766")
        self.assertEqual(received_commands[0]["params"]["DataOfCmd"], "KEY_HDMI")

    def test_helper_rejects_non_sysfs_paths(self) -> None:
        helper = Path(__file__).resolve().parents[1] / "scripts" / "switchdeck-helper"
        res_wake = subprocess.run(
            [sys.executable, str(helper), "set-wakeup", "/etc/passwd", "enabled"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(res_wake.returncode, 0)
        self.assertIn("Rejected", res_wake.stderr)

        res_usb = subprocess.run(
            [sys.executable, str(helper), "unbind-neptune", "../etc/shadow"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(res_usb.returncode, 0)
        self.assertIn("Rejected", res_usb.stderr)

    def test_travel_charge_override_resets_on_undock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mock = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD)
            coord = SwitchDeckCoordinator(mock, store=ProfileStore(Path(tmp)))
            coord.reconcile()
            mock.attach_samsung_s90c_hub(include_24g_xbox_dongle=False)
            self.assertEqual(coord.reconcile().charge_limit, 80)

            s_full = coord.set_travel_charge_100()
            self.assertEqual(s_full.charge_limit, -1)
            self.assertTrue(s_full.travel_charge_override)

            mock.detach_hub()
            s_undock = coord.reconcile()
            self.assertFalse(s_undock.travel_charge_override)
            self.assertEqual(s_undock.charge_limit, -1)

    def test_cli_demo_exits_zero(self) -> None:
        self.assertEqual(cli_main(["demo"]), 0)


class TestSecurityValidators(unittest.TestCase):
    def test_neptune_iface_and_wakeup_path_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            usb_root = root / "usb_devices"
            neptune_dev = usb_root / "3-3"
            neptune_dev.mkdir(parents=True)
            (neptune_dev / "idVendor").write_text("28de\n", encoding="utf-8")
            (neptune_dev / "idProduct").write_text("1205\n", encoding="utf-8")

            other_dev = usb_root / "3-4"
            other_dev.mkdir(parents=True)
            (other_dev / "idVendor").write_text("045e\n", encoding="utf-8")
            (other_dev / "idProduct").write_text("02fe\n", encoding="utf-8")

            self.assertTrue(validate_neptune_iface("3-3:1.0", usb_devices_root=usb_root))
            self.assertTrue(validate_neptune_iface("3-3:1.2", usb_devices_root=usb_root))
            self.assertFalse(validate_neptune_iface("3-4:1.0", usb_devices_root=usb_root))
            self.assertFalse(validate_neptune_iface("3-3:2.0", usb_devices_root=usb_root))
            self.assertFalse(validate_neptune_iface("../3-3:1.0", usb_devices_root=usb_root))
            self.assertFalse(validate_neptune_iface("3-3:1.0\n", usb_devices_root=usb_root))

            sys_root = root / "sys_devices"
            wakeup_node = sys_root / "pci0000:00" / "usb3" / "3-1" / "power" / "wakeup"
            wakeup_node.parent.mkdir(parents=True)
            wakeup_node.write_text("", encoding="utf-8")

            resolved = validate_wakeup_path(wakeup_node, sys_devices_root=str(sys_root))
            self.assertEqual(resolved, Path(os.path.realpath(wakeup_node)))
            self.assertTrue(safe_write_sysfs(resolved, "enabled"))  # type: ignore[arg-type]
            self.assertEqual(wakeup_node.read_text(encoding="utf-8"), "enabled")

            outside_wakeup = root / "outside" / "power" / "wakeup"
            outside_wakeup.parent.mkdir(parents=True)
            outside_wakeup.write_text("disabled", encoding="utf-8")
            traversal = sys_root / ".." / "outside" / "power" / "wakeup"
            self.assertIsNone(validate_wakeup_path(traversal, sys_devices_root=str(sys_root)))
            self.assertIsNone(
                validate_wakeup_path(sys_root / "pci0000:00" / "idVendor", sys_devices_root=str(sys_root))
            )

            symlink_wakeup = sys_root / "pci0000:00" / "power" / "wakeup"
            symlink_wakeup.parent.mkdir(parents=True)
            symlink_wakeup.symlink_to(outside_wakeup)
            self.assertIsNone(validate_wakeup_path(symlink_wakeup, sys_devices_root=str(sys_root)))
            self.assertFalse(safe_write_sysfs(symlink_wakeup, "enabled"))

    def test_tv_input_ssrf_crlf_and_pid_guards(self) -> None:
        self.assertEqual(validate_host(" 192.168.1.50 "), "192.168.1.50")
        self.assertEqual(validate_host("samsung-tv.local"), "samsung-tv.local")
        for bad_host in (
            "",
            "192.168.1.50\r\nInjected: true",
            "192.168.1.50\nfoo",
            "192.168.1.50/evil",
            "user@192.168.1.50",
            "tv.local?x=1",
            "tv.local:8002",
            "a" * 254,
        ):
            with self.assertRaises(ValueError):
                validate_host(bad_host)

        self.assertEqual(validate_port(8002), 8002)
        for bad_port in (0, -1, 65536, True, 8002.5):
            with self.assertRaises(ValueError):
                validate_port(bad_port)  # type: ignore[arg-type]

        self.assertEqual(validate_hdmi_input("hdmi2"), "HDMI2")
        self.assertEqual(validate_hdmi_input("tuner"), "Tuner")
        for bad_hdmi in ("HDMI2/../../PowerOff", "HDMI9", "HDMI1\r\n"):
            with self.assertRaises(ValueError):
                validate_hdmi_input(bad_hdmi)

        self.assertEqual(
            validate_webhook_url("https://ha.local:8123/api/webhook/switchdeck"),
            "https://ha.local:8123/api/webhook/switchdeck",
        )
        for bad_url in (
            "file:///etc/passwd",
            "ftp://192.168.1.10/x",
            "http://ha.local/hook\r\nX: 1",
            "http:///no-host",
        ):
            with self.assertRaises(ValueError):
                validate_webhook_url(bad_url)

        with tempfile.TemporaryDirectory() as tmp:
            proc_root = Path(tmp) / "proc"
            # System/low PIDs rejected
            self.assertEqual(validate_game_pid(1, proc_root=proc_root), (False, None))
            self.assertEqual(validate_game_pid(100, proc_root=proc_root), (False, None))
            self.assertEqual(validate_game_pid(os.getpid(), proc_root=proc_root), (False, None))

            # Protected comm rejected
            p_steam = proc_root / "2025"
            p_steam.mkdir(parents=True)
            (p_steam / "comm").write_text("gamescope-wl\n", encoding="utf-8")
            (p_steam / "stat").write_text(
                "2025 (gamescope-wl) S " + " ".join(["0"] * 18) + " 987654 0\n",
                encoding="utf-8",
            )
            self.assertEqual(validate_game_pid(2025, proc_root=proc_root), (False, None))

            # Valid game PID with space/paren in comm parses field 22 (starttime)
            p_game = proc_root / "4242"
            p_game.mkdir(parents=True)
            (p_game / "comm").write_text("Zelda64Recomp\n", encoding="utf-8")
            (p_game / "stat").write_text(
                "4242 (Zelda (64) Recomp) S " + " ".join(["0"] * 18) + " 5551234 0\n",
                encoding="utf-8",
            )
            self.assertEqual(validate_game_pid(4242, proc_root=proc_root), (True, "5551234"))
            self.assertEqual(capture_process_starttime(4242, proc_root=proc_root), "5551234")

    def test_atomic_write_json_permissions_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "config" / "state.json"
            atomic_write_json(target, {"token": "first"}, mode=0o600)
            self.assertTrue(target.is_file())
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"token": "first"})

            atomic_write_json(target, {"token": "second", "count": 2}, mode=0o600)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                json.loads(target.read_text(encoding="utf-8")),
                {"token": "second", "count": 2},
            )
            leftovers = [p.name for p in target.parent.iterdir() if p.name.startswith(".")]
            self.assertEqual(leftovers, [])


class TestUserSessionResolution(unittest.TestCase):
    def test_resolve_user_session_with_decky_env_and_xauthority(self) -> None:
        current_pw = pwd.getpwuid(os.getuid())
        with tempfile.TemporaryDirectory() as tmp:
            custom_home = Path(tmp) / "deck_home"
            custom_home.mkdir()
            xauth_file = custom_home / ".Xauthority"
            xauth_file.write_text("cookie", encoding="utf-8")

            ctx = resolve_user_session(
                {
                    "DECKY_USER": current_pw.pw_name,
                    "DECKY_USER_HOME": str(custom_home),
                }
            )
            self.assertEqual(ctx.uid, current_pw.pw_uid)
            self.assertEqual(ctx.gid, current_pw.pw_gid)
            self.assertEqual(ctx.home_dir, custom_home)
            self.assertEqual(ctx.runtime_dir, Path(f"/run/user/{current_pw.pw_uid}"))

            env = ctx.build_env()
            self.assertEqual(env["HOME"], str(custom_home))
            self.assertEqual(env["XDG_RUNTIME_DIR"], f"/run/user/{current_pw.pw_uid}")
            self.assertEqual(
                env["DBUS_SESSION_BUS_ADDRESS"],
                f"unix:path=/run/user/{current_pw.pw_uid}/bus",
            )
            self.assertEqual(env["XAUTHORITY"], str(xauth_file))

    def test_resolve_user_session_with_decky_user_uid_gid(self) -> None:
        fake_pw = pwd.struct_passwd(("deck", "x", 1000, 1000, "Steam Deck", "/home/deck", "/bin/bash"))
        with mock.patch("switchdeck.session.os.geteuid", return_value=0), mock.patch(
            "switchdeck.session.pwd.getpwnam", return_value=fake_pw
        ):
            ctx = resolve_user_session(
                {
                    "DECKY_USER": "deck",
                    "DECKY_USER_HOME": "/var/home/deck",
                }
            )
        self.assertEqual(ctx.uid, 1000)
        self.assertEqual(ctx.gid, 1000)
        self.assertEqual(ctx.username, "deck")
        self.assertEqual(ctx.home_dir, Path("/var/home/deck"))
        self.assertEqual(ctx.runtime_dir, Path("/run/user/1000"))
        self.assertTrue(ctx.is_root_host)
        env = ctx.build_env()
        self.assertEqual(env["XDG_RUNTIME_DIR"], "/run/user/1000")
        self.assertEqual(env["DBUS_SESSION_BUS_ADDRESS"], "unix:path=/run/user/1000/bus")


class TestProfileStoreAndDomainClamping(unittest.TestCase):
    def test_dock_profile_from_dict_clamps_bounds(self) -> None:
        clamped_hi = DockProfile.from_dict(
            {
                "profile_id": "test_hi",
                "docked_tdp_watts": 99,
                "handheld_tdp_watts": 25,
                "fsr_sharpness": 50,
                "docked_charge_limit": 150,
                "docked_volume": 1.8,
                "handheld_volume": 2.4,
                "preferred_container_width": 9999,
                "preferred_container_height": 4320,
            }
        )
        self.assertEqual(clamped_hi.docked_tdp_watts, 30)
        self.assertEqual(clamped_hi.handheld_tdp_watts, 15)
        self.assertEqual(clamped_hi.fsr_sharpness, 20)
        self.assertEqual(clamped_hi.docked_charge_limit, 100)
        self.assertAlmostEqual(clamped_hi.docked_volume, 1.0)
        self.assertAlmostEqual(clamped_hi.handheld_volume, 1.0)
        self.assertEqual(clamped_hi.preferred_container_width, 3840)
        self.assertEqual(clamped_hi.preferred_container_height, 2160)

        clamped_lo = DockProfile.from_dict(
            {
                "profile_id": "test_lo",
                "docked_tdp_watts": 0,
                "handheld_tdp_watts": 1,
                "fsr_sharpness": -5,
                "docked_charge_limit": 15,
                "docked_volume": -0.5,
                "handheld_volume": -1.0,
                "preferred_container_width": 320,
                "preferred_container_height": 200,
            }
        )
        self.assertEqual(clamped_lo.docked_tdp_watts, 3)
        self.assertEqual(clamped_lo.handheld_tdp_watts, 3)
        self.assertEqual(clamped_lo.fsr_sharpness, 0)
        self.assertEqual(clamped_lo.docked_charge_limit, 50)
        self.assertAlmostEqual(clamped_lo.docked_volume, 0.0)
        self.assertAlmostEqual(clamped_lo.handheld_volume, 0.0)
        self.assertEqual(clamped_lo.preferred_container_width, 640)
        self.assertEqual(clamped_lo.preferred_container_height, 480)

        special = DockProfile.from_dict(
            {
                "profile_id": "test_special",
                "docked_charge_limit": -1,
                "docked_tdp_watts": True,
                "docked_volume": float("nan"),
                "handheld_volume": float("inf"),
            }
        )
        self.assertEqual(special.docked_charge_limit, -1)
        self.assertEqual(special.docked_tdp_watts, 15)
        self.assertAlmostEqual(special.docked_volume, 0.65)
        self.assertAlmostEqual(special.handheld_volume, 0.50)

    def test_profile_store_settings_priority_permissions_cert_pins_and_legacy_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decky_dir = root / "decky_settings"
            xdg_dir = root / "xdg_config"
            decky_home = root / "decky_home"

            with mock.patch.dict(
                os.environ,
                {
                    "DECKY_PLUGIN_SETTINGS_DIR": str(decky_dir),
                    "XDG_CONFIG_HOME": str(xdg_dir),
                    "DECKY_USER_HOME": str(decky_home),
                },
                clear=False,
            ):
                self.assertEqual(default_config_dir(), decky_dir)

            # Backwards compatibility with legacy plain-string tv_tokens.json
            decky_dir.mkdir(parents=True)
            (decky_dir / "tv_tokens.json").write_text(
                json.dumps({"192.168.1.50": "legacy_tok_123"}),
                encoding="utf-8",
            )
            store = ProfileStore(decky_dir)
            self.assertEqual(store.get_token("192.168.1.50"), "legacy_tok_123")
            self.assertEqual(store.get_cert_fingerprint("192.168.1.50"), "")

            fp_hex = "AABBCCDD" * 8
            store.set_cert_fingerprint("192.168.1.50", fp_hex)
            self.assertEqual(store.profiles_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(store.tokens_path.stat().st_mode & 0o777, 0o600)

            reloaded = ProfileStore(decky_dir)
            self.assertEqual(reloaded.get_token("192.168.1.50"), "legacy_tok_123")
            self.assertEqual(reloaded.get_cert_fingerprint("192.168.1.50"), fp_hex.lower())

            reloaded.clear_cert_fingerprint("192.168.1.50")
            reloaded2 = ProfileStore(decky_dir)
            self.assertEqual(reloaded2.get_cert_fingerprint("192.168.1.50"), "")
            self.assertEqual(reloaded2.get_token("192.168.1.50"), "legacy_tok_123")


class TestSamsungTlsTofuAndWsHardening(unittest.TestCase):
    @staticmethod
    def _generate_self_signed_cert(tmp_dir: Path, name: str) -> tuple[Path, Path, str]:
        openssl_bin = shutil.which("openssl")
        assert openssl_bin is not None, "openssl binary required for TLS TOFU test"
        cert_pem = tmp_dir / f"{name}.crt"
        key_pem = tmp_dir / f"{name}.key"
        cert_der = tmp_dir / f"{name}.der"
        subprocess.run(
            [
                openssl_bin,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(key_pem),
                "-out",
                str(cert_pem),
                "-days",
                "1",
                "-nodes",
                "-subj",
                f"/CN=switchdeck-{name}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [openssl_bin, "x509", "-in", str(cert_pem), "-outform", "DER", "-out", str(cert_der)],
            check=True,
            capture_output=True,
            text=True,
        )
        fp = hashlib.sha256(cert_der.read_bytes()).hexdigest().lower()
        return cert_pem, key_pem, fp

    def test_tofu_sha256_tls_pinning_and_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cert1, key1, fp1 = self._generate_self_signed_cert(tmp_path, "tv1")
            cert2, key2, fp2 = self._generate_self_signed_cert(tmp_path, "tv2")
            self.assertNotEqual(fp1, fp2)

            active_cert: list[tuple[Path, Path]] = [(cert1, key1)]
            stop_srv = threading.Event()
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.bind(("127.0.0.1", 0))
            srv.listen(8)
            srv.settimeout(0.2)
            port = srv.getsockname()[1]

            def tls_server() -> None:
                while not stop_srv.is_set():
                    try:
                        conn, _ = srv.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    try:
                        c_path, k_path = active_cert[0]
                        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                        ctx.load_cert_chain(certfile=str(c_path), keyfile=str(k_path))
                        with ctx.wrap_socket(conn, server_side=True) as tls_conn:
                            req = tls_conn.recv(4096).decode("ascii", errors="ignore")
                            if "sec-websocket-key:" not in req.lower():
                                continue
                            key_line = [
                                ln for ln in req.splitlines() if ln.lower().startswith("sec-websocket-key:")
                            ][0]
                            ws_key = key_line.split(":", 1)[1].strip()
                            accept = base64.b64encode(
                                hashlib.sha1((ws_key + WS_GUID).encode("ascii")).digest()
                            ).decode("ascii")
                            tls_conn.sendall(
                                f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                                f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n".encode("ascii")
                            )
                            tls_conn.sendall(
                                _encode_unmasked_ws_frame(
                                    json.dumps({"event": "ms.channel.connect", "data": {"token": "tok_tls_01"}})
                                )
                            )
                            tls_conn.recv(4096)
                    except (OSError, ssl.SSLError):
                        pass
                    finally:
                        try:
                            conn.close()
                        except OSError:
                            pass

            t = threading.Thread(target=tls_server, daemon=True)
            t.start()
            try:
                store = ProfileStore(tmp_path / "cfg")
                client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                client_ctx.check_hostname = False
                client_ctx.verify_mode = ssl.CERT_NONE

                driver = SamsungTizenDriver(
                    get_token=store.get_token,
                    set_token=store.set_token,
                    ssl_context=client_ctx,
                    get_cert_fingerprint=store.get_cert_fingerprint,
                    set_cert_fingerprint=store.set_cert_fingerprint,
                )

                # 1. First pair pins cert1 SHA-256
                tok = driver.pair("127.0.0.1", port=port)
                self.assertEqual(tok, "tok_tls_01")
                self.assertEqual(store.get_cert_fingerprint("127.0.0.1"), fp1)

                # 2. Matching cert succeeds
                tok2 = driver.send_key("127.0.0.1", port=port, key_name="KEY_HDMI")
                self.assertEqual(tok2, "tok_tls_01")

                # 3. Swapped cert2 triggers SSLCertVerificationError
                active_cert[0] = (cert2, key2)
                with self.assertRaises(ssl.SSLCertVerificationError):
                    driver.send_key("127.0.0.1", port=port, key_name="KEY_HDMI")

                # 4. trust_new_cert=True rotates pin to cert2
                tok3 = driver.pair("127.0.0.1", port=port, trust_new_cert=True)
                self.assertEqual(tok3, "tok_tls_01")
                self.assertEqual(store.get_cert_fingerprint("127.0.0.1"), fp2)

                # 5. Swap back to cert1 and verify CLI `pair-samsung --trust-new-cert` rotates pin
                active_cert[0] = (cert1, key1)
                with mock.patch.dict(os.environ, {"DECKY_PLUGIN_SETTINGS_DIR": str(tmp_path / "cfg")}):
                    with mock.patch(
                        "switchdeck.cli.SamsungTizenDriver",
                        side_effect=lambda **kw: SamsungTizenDriver(ssl_context=client_ctx, **kw),
                    ):
                        rc = cli_main(
                            ["pair-samsung", "127.0.0.1", "--port", str(port), "--trust-new-cert"]
                        )
                self.assertEqual(rc, 0)
                self.assertEqual(ProfileStore(tmp_path / "cfg").get_cert_fingerprint("127.0.0.1"), fp1)
            finally:
                stop_srv.set()
                srv.close()
                t.join(timeout=2.0)

    def test_ws_ping_pong_and_size_bounds(self) -> None:
        # 1. Ping -> Pong handling before greeting frame
        pong_received: list[tuple[int, bytes]] = []
        srv1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv1.bind(("127.0.0.1", 0))
        srv1.listen(1)
        port1 = srv1.getsockname()[1]

        def ping_server() -> None:
            conn, _ = srv1.accept()
            with conn:
                req = conn.recv(4096).decode("ascii")
                ws_key = [ln for ln in req.splitlines() if ln.lower().startswith("sec-websocket-key:")][0].split(":", 1)[1].strip()
                accept = base64.b64encode(hashlib.sha1((ws_key + WS_GUID).encode("ascii")).digest()).decode("ascii")
                conn.sendall(
                    f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                    f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n".encode("ascii")
                )
                # Send unmasked Ping (opcode 0x9) with payload b"ping!"
                conn.sendall(bytes([0x89, 5]) + b"ping!")
                # Read client masked Pong (opcode 0xA)
                hdr = conn.recv(2)
                plen = hdr[1] & 0x7F
                mask = conn.recv(4)
                masked_payload = conn.recv(plen)
                unmasked = bytes(b ^ mask[i % 4] for i, b in enumerate(masked_payload))
                pong_received.append((hdr[0] & 0x0F, unmasked))
                # Now send greeting and absorb remote key command
                conn.sendall(_encode_unmasked_ws_frame(json.dumps({"event": "ms.channel.connect", "data": {"token": "pong_ok"}})))
                conn.recv(4096)

        t1 = threading.Thread(target=ping_server, daemon=True)
        t1.start()
        tokens: dict[str, str] = {}
        driver = SamsungTizenDriver(get_token=lambda h: tokens.get(h, ""), set_token=lambda h, v: tokens.__setitem__(h, v))
        tok = driver.send_key("127.0.0.1", port1, "KEY_HDMI")
        t1.join(timeout=2.0)
        srv1.close()
        self.assertEqual(tok, "pong_ok")
        self.assertEqual(pong_received, [(0xA, b"ping!")])

        # 2. Oversized >16384B HTTP handshake rejected
        srv2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv2.bind(("127.0.0.1", 0))
        srv2.listen(1)
        port2 = srv2.getsockname()[1]

        def huge_handshake_server() -> None:
            conn, _ = srv2.accept()
            with conn:
                conn.recv(4096)
                try:
                    conn.sendall(b"HTTP/1.1 101 Switching Protocols\r\nX-Pad: " + b"A" * 17000 + b"\r\n\r\n")
                except OSError:
                    pass

        t2 = threading.Thread(target=huge_handshake_server, daemon=True)
        t2.start()
        with self.assertRaises(ConnectionError):
            driver.send_key("127.0.0.1", port2, "KEY_HDMI")
        t2.join(timeout=2.0)
        srv2.close()

        # 3. Oversized >65536B WS payload rejected
        srv3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv3.bind(("127.0.0.1", 0))
        srv3.listen(1)
        port3 = srv3.getsockname()[1]

        def huge_frame_server() -> None:
            conn, _ = srv3.accept()
            with conn:
                req = conn.recv(4096).decode("ascii")
                ws_key = [ln for ln in req.splitlines() if ln.lower().startswith("sec-websocket-key:")][0].split(":", 1)[1].strip()
                accept = base64.b64encode(hashlib.sha1((ws_key + WS_GUID).encode("ascii")).digest()).decode("ascii")
                conn.sendall(
                    f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                    f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n".encode("ascii")
                )
                # Declare 65537-byte payload via 64-bit extended length (127)
                conn.sendall(bytes([0x81, 127]) + struct.pack("!Q", 65537))

        t3 = threading.Thread(target=huge_frame_server, daemon=True)
        t3.start()
        with self.assertRaises(_WsPayloadTooLarge):
            driver.send_key("127.0.0.1", port3, "KEY_HDMI")
        t3.join(timeout=2.0)
        srv3.close()


class TestLinuxHardwareBackendHardening(unittest.TestCase):
    def test_dongle_pipe_pollin_promotion_and_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input19 = root / "input19"
            (input19 / "device" / "power").mkdir(parents=True)
            (input19 / "device" / "power" / "wakeup_count").write_text("0\n", encoding="utf-8")
            (input19 / "event19").write_text("", encoding="utf-8")

            input20 = root / "input20"
            (input20 / "device" / "power").mkdir(parents=True)
            (input20 / "device" / "power" / "wakeup_count").write_text("0\n", encoding="utf-8")
            (input20 / "event20").write_text("", encoding="utf-8")

            r_fd1, w_fd1 = os.pipe()
            r_fd2, w_fd2 = os.pipe()
            os.set_blocking(r_fd1, False)
            os.set_blocking(r_fd2, False)
            orig_open = os.open

            def _fake_open(path: object, flags: int, *args: object) -> int:
                p_str = os.fspath(path)
                if p_str == "/dev/input/event19":
                    return r_fd1
                if p_str == "/dev/input/event20":
                    return r_fd2
                return orig_open(path, flags, *args)  # type: ignore[arg-type]

            backend = LinuxHardwareBackend()
            try:
                with mock.patch("switchdeck.backends.linux.os.open", side_effect=_fake_open):
                    # Sleeping initially -> False
                    self.assertEqual(backend._is_dongle_actively_awake(input19, "dongle_24g"), (False, 0))
                    self.assertIn(str(input19), backend._dongle_watch_fds)

                    # Readable POLLIN event -> promotes to True
                    os.write(w_fd1, b"\x01\x00\x00\x00")
                    self.assertEqual(backend._is_dongle_actively_awake(input19, "dongle_24g"), (True, 0))

                    # Second sleeping dongle fd stays open until close()
                    self.assertEqual(backend._is_dongle_actively_awake(input20, "dongle_24g"), (False, 0))
                    self.assertIn(str(input20), backend._dongle_watch_fds)

                    backend.close()
                    self.assertEqual(backend._dongle_watch_fds, {})
                    with self.assertRaises(OSError):
                        os.fstat(r_fd2)
            finally:
                for fd in (r_fd1, w_fd1, r_fd2, w_fd2):
                    try:
                        os.close(fd)
                    except OSError:
                        pass

    def test_is_ac_online_skips_device_scope_and_accepts_mains(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ps_root = Path(tmp) / "power_supply"
            ctrl_bat = ps_root / "sony_controller_battery_00"
            ctrl_bat.mkdir(parents=True)
            (ctrl_bat / "scope").write_text("Device\n", encoding="utf-8")
            (ctrl_bat / "type").write_text("USB\n", encoding="utf-8")
            (ctrl_bat / "online").write_text("1\n", encoding="utf-8")

            backend = LinuxHardwareBackend()
            self.assertFalse(backend.is_ac_online(power_supply_root=ps_root))

            ac_dir = ps_root / "ACAD"
            ac_dir.mkdir(parents=True)
            (ac_dir / "scope").write_text("System\n", encoding="utf-8")
            (ac_dir / "type").write_text("Mains\n", encoding="utf-8")
            (ac_dir / "online").write_text("1\n", encoding="utf-8")
            self.assertTrue(backend.is_ac_online(power_supply_root=ps_root))


class TestCoordinatorHardening(unittest.TestCase):
    def test_undock_sigcont_guaranteed_and_keep_builtin_resets_when_scaling_raises(self) -> None:
        class FailingUndockScalingMock(MockHardwareBackend):
            fail_scaling: bool = False

            def apply_gamescope_scaling(self, decision, server_idx: int = 1) -> bool:  # type: ignore[override]
                if self.fail_scaling:
                    raise RuntimeError("Simulated X11 failure during undock")
                return super().apply_gamescope_scaling(decision, server_idx=server_idx)

        with tempfile.TemporaryDirectory() as tmp:
            mock_hw = FailingUndockScalingMock(deck_model=DeckModel.JUPITER_LCD)
            coord = SwitchDeckCoordinator(mock_hw, store=ProfileStore(Path(tmp)))
            coord.reconcile()

            mock_hw.attach_samsung_s90c_hub(include_24g_xbox_dongle=True, pad_awake=True)
            coord.reconcile()
            s_keep = coord.set_keep_builtin(True)
            self.assertTrue(s_keep.manual_keep_builtin)

            mock_hw.active_game = GameWindowState(
                pid=4242, app_id=10, window_id=20, server_idx=1,
                width=1920, height=1080, gpu_busy_percent=65, title="Zelda64Recompiled",
            )
            mock_hw.fail_scaling = True
            mock_hw.detach_hub(keep_wireless_controller=True)
            with self.assertRaises(RuntimeError):
                coord.reconcile()

            self.assertNotIn(4242, mock_hw.paused_pids)
            self.assertIn("kill:SIGSTOP pid=4242", mock_hw.events_log)
            self.assertIn("kill:SIGCONT pid=4242", mock_hw.events_log)
            self.assertFalse(coord.manual_keep_builtin)

    def test_transition_seq_and_qam_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mock_hw = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD)
            coord = SwitchDeckCoordinator(mock_hw, store=ProfileStore(Path(tmp)))

            # Handheld cold boot must NOT increment transition_seq
            s0 = coord.reconcile()
            self.assertEqual(s0.transition_seq, 0)
            self.assertIsNone(s0.last_transition)
            self.assertEqual(coord.reconcile().transition_seq, 0)

            # Dock increments transition_seq to 1
            mock_hw.attach_samsung_s90c_hub(include_24g_xbox_dongle=True, pad_awake=True)
            s1 = coord.reconcile()
            self.assertEqual(s1.transition_seq, 1)
            assert s1.last_transition is not None
            self.assertEqual(s1.last_transition["kind"], "docked")
            self.assertFalse(s1.builtin_controller_bound)

            # Steady-state reconcile does not increment transition_seq
            self.assertEqual(coord.reconcile().transition_seq, 1)

            # QAM controls
            s_keep = coord.set_keep_builtin(True)
            self.assertTrue(s_keep.manual_keep_builtin)
            self.assertTrue(s_keep.builtin_controller_bound)

            s_chg = coord.set_travel_charge_override(True)
            self.assertTrue(s_chg.travel_charge_override)
            self.assertEqual(s_chg.charge_limit, -1)
            s_chg_off = coord.set_travel_charge_override(False)
            self.assertFalse(s_chg_off.travel_charge_override)
            self.assertEqual(s_chg_off.charge_limit, 80)

            updated = coord.update_active_profile({"docked_tdp_watts": 99, "fsr_sharpness": 5})
            self.assertEqual(updated.docked_tdp_watts, 30)
            self.assertEqual(updated.fsr_sharpness, 5)
            self.assertEqual(coord.reconcile().tdp_watts, 30)

            # Undock increments transition_seq to 2 and resets manual overrides
            mock_hw.detach_hub(keep_wireless_controller=True)
            s2 = coord.reconcile()
            self.assertEqual(s2.transition_seq, 2)
            assert s2.last_transition is not None
            self.assertEqual(s2.last_transition["kind"], "undocked")
            self.assertFalse(s2.manual_keep_builtin)


class TestDaemonUnixSocketIpc(unittest.IsolatedAsyncioTestCase):
    async def test_daemon_live_unix_socket_ipc(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sock_path = tmp_path / "sd.sock"
            cfg_dir = tmp_path / "cfg"
            mock_hw = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD)
            mock_hw.attach_samsung_s90c_hub(include_24g_xbox_dongle=True, pad_awake=True)

            with mock.patch.dict(os.environ, {"DECKY_PLUGIN_SETTINGS_DIR": str(cfg_dir)}):
                daemon = SwitchDeckDaemon(
                    backend=mock_hw,
                    socket_path=sock_path,
                    observer_interval_sec=5.0,
                    debounce_sec=0.05,
                )
                task = asyncio.create_task(daemon.run())
                try:
                    for _ in range(50):
                        if sock_path.exists():
                            break
                        await asyncio.sleep(0.02)
                    self.assertTrue(sock_path.exists())
                    self.assertEqual(sock_path.stat().st_mode & 0o777, 0o600)

                    async def _rpc(payload: dict) -> dict:
                        reader, writer = await asyncio.open_unix_connection(str(sock_path))
                        try:
                            writer.write((json.dumps(payload) + "\n").encode("utf-8"))
                            await writer.drain()
                            raw = await asyncio.wait_for(reader.readline(), timeout=2.0)
                            return json.loads(raw.decode("utf-8"))
                        finally:
                            writer.close()
                            await writer.wait_closed()

                    r_status = await _rpc({"cmd": "status"})
                    self.assertTrue(r_status["ok"])
                    self.assertEqual(r_status["status"]["deck_model"], "Jupiter")
                    self.assertFalse(r_status["status"]["builtin_controller_bound"])

                    r_prof = await _rpc({"cmd": "update_profile", "patch": {"docked_tdp_watts": 99}})
                    self.assertTrue(r_prof["ok"])
                    self.assertEqual(r_prof["profile"]["docked_tdp_watts"], 30)

                    r_rebind = await _rpc({"cmd": "rebind_builtin"})
                    self.assertTrue(r_rebind["ok"])
                    self.assertTrue(r_rebind["status"]["builtin_controller_bound"])
                finally:
                    daemon._stop_event.set()
                    await asyncio.wait_for(task, timeout=3.0)

            self.assertFalse(sock_path.exists())
            self.assertTrue(mock_hw.is_builtin_controller_bound())


class TestDeckyPluginLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_main_plugin_rpcs_transition_emit_and_unload_rebind(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        repo_root_str = str(repo_root)
        added_repo_path = False
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)
            added_repo_path = True

        with tempfile.TemporaryDirectory() as tmp:
            settings_dir = Path(tmp) / "decky_settings"
            emitted: list[tuple[str, dict]] = []

            fake_decky = types.ModuleType("decky")
            fake_decky.logger = logging.getLogger("switchdeck.test_decky")  # type: ignore[attr-defined]
            fake_decky.DECKY_PLUGIN_SETTINGS_DIR = str(settings_dir)  # type: ignore[attr-defined]
            fake_decky.DECKY_USER = ""  # type: ignore[attr-defined]
            fake_decky.DECKY_USER_HOME = ""  # type: ignore[attr-defined]

            async def _emit(event: str, payload: dict) -> None:
                emitted.append((event, payload))

            fake_decky.emit = _emit  # type: ignore[attr-defined]

            orig_decky = sys.modules.get("decky")
            orig_main = sys.modules.get("main")
            env_patch = {
                "DECKY_PLUGIN_SETTINGS_DIR": "",
                "DECKY_USER": "",
                "DECKY_USER_HOME": "",
                "XDG_CONFIG_HOME": str(Path(tmp) / "xdg"),
            }
            mock_hw = MockHardwareBackend(deck_model=DeckModel.JUPITER_LCD)

            try:
                sys.modules["decky"] = fake_decky
                with mock.patch.dict(os.environ, env_patch):
                    os.environ.pop("DECKY_PLUGIN_SETTINGS_DIR", None)
                    main_mod = importlib.import_module("main")
                    main_mod = importlib.reload(main_mod)

                    plugin = main_mod.Plugin()
                    with mock.patch.object(main_mod, "LinuxHardwareBackend", return_value=mock_hw):
                        await plugin._main()
                        self.assertIsNotNone(plugin.coordinator)
                        self.assertEqual(emitted, [])

                        # Dock transition emits switchdeck_transition via decky.emit
                        mock_hw.attach_samsung_s90c_hub(include_24g_xbox_dongle=True, pad_awake=True)
                        st = await plugin.get_status()
                        self.assertTrue(st["is_docked"])
                        self.assertFalse(st["builtin_controller_bound"])
                        self.assertEqual(len(emitted), 1)
                        self.assertEqual(emitted[0][0], "switchdeck_transition")
                        self.assertEqual(emitted[0][1]["kind"], "docked")

                        prof = await plugin.get_active_profile()
                        self.assertEqual(prof["display_name"], "SAMSUNG S90C")

                        upd = await plugin.update_profile({"docked_tdp_watts": 22})
                        self.assertEqual(upd["docked_tdp_watts"], 22)

                        st_keep = await plugin.set_keep_builtin(True)
                        self.assertTrue(st_keep["builtin_controller_bound"])

                        st_chg = await plugin.set_charge_override(True)
                        self.assertEqual(st_chg["charge_limit"], -1)

                        st_rebind = await plugin.rebind_builtin()
                        self.assertTrue(st_rebind["builtin_controller_bound"])

                        # Restore auto-unbind before testing _unload failsafe
                        st_unbind = await plugin.set_keep_builtin(False)
                        self.assertFalse(st_unbind["builtin_controller_bound"])

                        await plugin._unload()
                        self.assertTrue(mock_hw.is_builtin_controller_bound())
                        self.assertFalse(mock_hw.get_lcd_bluetooth_wakeup())
            finally:
                if orig_decky is None:
                    sys.modules.pop("decky", None)
                else:
                    sys.modules["decky"] = orig_decky
                if orig_main is None:
                    sys.modules.pop("main", None)
                else:
                    sys.modules["main"] = orig_main
                if added_repo_path:
                    try:
                        sys.path.remove(repo_root_str)
                    except ValueError:
                        pass


class TestDeckyZipIntegrity(unittest.TestCase):
    def test_decky_zip_package_structure(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        zip_path = repo_root / "dist-zip" / "SwitchDeck-v0.2.0.zip"
        self.assertTrue(
            zip_path.is_file(),
            f"Missing Decky ZIP at {zip_path}; run ./scripts/build_decky_zip.sh",
        )
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            self.assertIn("SwitchDeck/plugin.json", names)
            self.assertIn("SwitchDeck/dist/index.js", names)
            self.assertIn("SwitchDeck/py_modules/switchdeck/coordinator.py", names)
            self.assertIn("SwitchDeck/main.py", names)

            plugin_meta = json.loads(zf.read("SwitchDeck/plugin.json").decode("utf-8"))
            self.assertIn("root", plugin_meta.get("flags", []))

            dist_info = zf.getinfo("SwitchDeck/dist/index.js")
            self.assertGreater(dist_info.file_size, 0)

            for entry in names:
                self.assertNotIn("__pycache__", entry)
                self.assertFalse(entry.endswith(".pyc"), f"Unexpected bytecode in ZIP: {entry}")


if __name__ == "__main__":
    unittest.main()
