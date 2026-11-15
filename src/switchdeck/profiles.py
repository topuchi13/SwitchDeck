"""JSON persistence for per-EDID dock profiles and TV pairing tokens."""

from __future__ import annotations

from dataclasses import replace
import json
import os
import threading
from pathlib import Path
from typing import Any

from .domain import DockProfile
from .security import atomic_write_json
from .session import resolve_user_session


def default_config_dir() -> Path:
    """Resolve persistent SwitchDeck config directory across Decky, XDG, and local environments."""
    decky_settings = os.environ.get("DECKY_PLUGIN_SETTINGS_DIR")
    if decky_settings:
        return Path(decky_settings)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "switchdeck"
    decky_home = os.environ.get("DECKY_USER_HOME")
    if decky_home:
        return Path(decky_home) / ".config" / "switchdeck"
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return resolve_user_session().home_dir / ".config" / "switchdeck"
    return Path.home() / ".config" / "switchdeck"


class ProfileStore:
    """Manages EDID-keyed dock profiles and persisted Smart TV auth tokens & TLS pins."""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or default_config_dir()
        self.profiles_path = self.config_dir / "profiles.json"
        self.tokens_path = self.config_dir / "tv_tokens.json"
        self._lock = threading.RLock()
        self._profiles: dict[str, DockProfile] = {}
        self._tokens: dict[str, str] = {}
        self._cert_fingerprints: dict[str, str] = {}
        self._profiles_mtime_ns: int | None = None
        self._tokens_mtime_ns: int | None = None
        self.load()

    @staticmethod
    def _stat_mtime_ns(path: Path) -> int | None:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return None

    @staticmethod
    def _clone_profile(profile: DockProfile) -> DockProfile:
        return replace(
            profile,
            tv=replace(profile.tv),
            overclock=replace(profile.overclock),
        )

    def _load_profiles_locked(self) -> None:
        self._profiles = {}
        if self.profiles_path.is_file():
            try:
                raw = json.loads(self.profiles_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._profiles = {
                        str(pid): DockProfile.from_dict(pdata)
                        for pid, pdata in raw.items()
                        if isinstance(pdata, dict)
                    }
            except (OSError, ValueError):
                self._profiles = {}
        if "default" not in self._profiles:
            self._profiles["default"] = DockProfile(profile_id="default", display_name="Default Dock")
        self._profiles_mtime_ns = self._stat_mtime_ns(self.profiles_path)

    def _load_tokens_locked(self) -> None:
        self._tokens = {}
        self._cert_fingerprints = {}
        if self.tokens_path.is_file():
            try:
                raw_tokens = json.loads(self.tokens_path.read_text(encoding="utf-8"))
                if isinstance(raw_tokens, dict):
                    for raw_host, entry in raw_tokens.items():
                        host = str(raw_host)
                        if isinstance(entry, dict):
                            tok = entry.get("token")
                            fp = entry.get("cert_sha256")
                            if tok is not None and str(tok):
                                self._tokens[host] = str(tok)
                            if fp is not None and str(fp):
                                self._cert_fingerprints[host] = str(fp).strip().lower()
                        elif entry is not None:
                            tok_str = str(entry)
                            if tok_str:
                                self._tokens[host] = tok_str
            except (OSError, ValueError):
                self._tokens = {}
                self._cert_fingerprints = {}
        self._tokens_mtime_ns = self._stat_mtime_ns(self.tokens_path)

    def _refresh_if_changed_locked(self) -> None:
        cur_prof = self._stat_mtime_ns(self.profiles_path)
        if cur_prof != self._profiles_mtime_ns:
            self._load_profiles_locked()
        cur_tok = self._stat_mtime_ns(self.tokens_path)
        if cur_tok != self._tokens_mtime_ns:
            self._load_tokens_locked()

    def load(self) -> None:
        with self._lock:
            self._load_profiles_locked()
            self._load_tokens_locked()

    def save(self) -> None:
        with self._lock:
            session = resolve_user_session()
            uid = session.uid if session.is_root_host and session.uid != 0 else None
            gid = session.gid if session.is_root_host and session.uid != 0 else None

            payload = {pid: prof.to_dict() for pid, prof in self._profiles.items()}
            tokens_payload: dict[str, Any] = {}
            for host in sorted(set(self._tokens) | set(self._cert_fingerprints)):
                tok = self._tokens.get(host, "")
                fp = self._cert_fingerprints.get(host, "")
                if fp:
                    tokens_payload[host] = {"token": tok, "cert_sha256": fp}
                elif tok:
                    tokens_payload[host] = tok

            atomic_write_json(self.profiles_path, payload, mode=0o600, uid=uid, gid=gid)
            atomic_write_json(self.tokens_path, tokens_payload, mode=0o600, uid=uid, gid=gid)
            self._profiles_mtime_ns = self._stat_mtime_ns(self.profiles_path)
            self._tokens_mtime_ns = self._stat_mtime_ns(self.tokens_path)

    def get_profile(self, profile_id: str | None, display_name: str | None = None) -> DockProfile:
        with self._lock:
            self._refresh_if_changed_locked()
            key = profile_id or "default"
            if key not in self._profiles:
                default = self._profiles["default"]
                self._profiles[key] = DockProfile(
                    profile_id=key,
                    display_name=display_name or key,
                    preferred_container_width=default.preferred_container_width,
                    preferred_container_height=default.preferred_container_height,
                    fsr_sharpness=default.fsr_sharpness,
                    docked_tdp_watts=default.docked_tdp_watts,
                    handheld_tdp_watts=default.handheld_tdp_watts,
                    docked_charge_limit=default.docked_charge_limit,
                    docked_volume=default.docked_volume,
                    handheld_volume=default.handheld_volume,
                    auto_pause_on_undock=default.auto_pause_on_undock,
                    adaptive_gpu_downscale=default.adaptive_gpu_downscale,
                    tv=replace(default.tv),
                    overclock=replace(default.overclock),
                )
                self.save()
            return self._clone_profile(self._profiles[key])

    def get_handheld_profile(self) -> DockProfile:
        with self._lock:
            self._refresh_if_changed_locked()
            return self._clone_profile(self._profiles["default"])

    def put_profile(self, profile: DockProfile) -> None:
        with self._lock:
            self._refresh_if_changed_locked()
            self._profiles[profile.profile_id] = self._clone_profile(profile)
            self.save()

    @staticmethod
    def _scoped_token_key(driver: str, host: str) -> str:
        drv = (driver or "").strip().lower()
        if drv in ("", "samsung_tizen"):
            return host
        return f"{drv}:{host}"

    def get_driver_token(self, driver: str, host: str) -> str:
        with self._lock:
            self._refresh_if_changed_locked()
            key = self._scoped_token_key(driver, host)
            return self._tokens.get(key, "")

    def set_driver_token(self, driver: str, host: str, token: str) -> None:
        with self._lock:
            self._refresh_if_changed_locked()
            key = self._scoped_token_key(driver, host)
            if token == "":
                self._tokens.pop(key, None)
            else:
                self._tokens[key] = token
            self.save()

    def get_token(self, host: str) -> str:
        with self._lock:
            self._refresh_if_changed_locked()
            return self._tokens.get(host, "")

    def set_token(self, host: str, token: str) -> None:
        with self._lock:
            self._refresh_if_changed_locked()
            if token == "":
                self._tokens.pop(host, None)
            else:
                self._tokens[host] = token
            self.save()

    def get_cert_fingerprint(self, host: str) -> str:
        with self._lock:
            self._refresh_if_changed_locked()
            return self._cert_fingerprints.get(host, "")

    def set_cert_fingerprint(self, host: str, sha256_hex: str) -> None:
        with self._lock:
            self._refresh_if_changed_locked()
            self._cert_fingerprints[host] = sha256_hex.strip().lower()
            self.save()

    def clear_cert_fingerprint(self, host: str) -> None:
        with self._lock:
            self._refresh_if_changed_locked()
            if host in self._cert_fingerprints:
                self._cert_fingerprints.pop(host, None)
                self.save()
