"""User session resolution and privilege-dropped command execution for SwitchDeck."""

from __future__ import annotations

import os
import pwd
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class UserSessionContext:
    """Target SteamOS desktop/gamepad user context when running directly or under root."""

    uid: int
    gid: int
    username: str
    home_dir: Path
    runtime_dir: Path
    is_root_host: bool

    def _discover_xauthority(self) -> Path | None:
        try:
            if self.runtime_dir.is_dir():
                matches = sorted(self.runtime_dir.glob("xauth_*"))
                if matches:
                    return matches[0]
        except OSError:
            pass
        home_xauth = self.home_dir / ".Xauthority"
        try:
            if home_xauth.exists():
                return home_xauth
        except OSError:
            pass
        return None

    def build_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build an environment dictionary targeting the resolved user session."""
        env = os.environ.copy()
        env["HOME"] = str(self.home_dir)
        env["USER"] = self.username
        env["LOGNAME"] = self.username
        env["XDG_RUNTIME_DIR"] = str(self.runtime_dir)
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={self.runtime_dir}/bus"
        env["PULSE_RUNTIME_PATH"] = f"{self.runtime_dir}/pulse"

        xauth = self._discover_xauthority()
        if xauth is not None:
            env["XAUTHORITY"] = str(xauth)
        elif self.is_root_host:
            env.pop("XAUTHORITY", None)

        if extra:
            env.update(extra)
        return env

    def run_user_cmd(
        self,
        cmd: list[str],
        extra_env: dict[str, str] | None = None,
        timeout: float = 2.5,
    ) -> tuple[int, str]:
        """Execute a session-scoped command, dropping root privileges when hosted as root."""
        env = self.build_env(extra_env)
        kwargs: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "timeout": timeout,
            "check": False,
            "env": env,
        }
        drop_privs = self.is_root_host and self.uid != 0
        try:
            if drop_privs:
                try:
                    proc = subprocess.run(cmd, user=self.uid, group=self.gid, **kwargs)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    proc = subprocess.run(cmd, **kwargs)  # type: ignore[arg-type]
            else:
                proc = subprocess.run(cmd, **kwargs)  # type: ignore[arg-type]
            return proc.returncode, proc.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return 1, ""


def _lookup_passwd_name(username: str) -> pwd.struct_passwd | None:
    if not username or username == "root":
        return None
    try:
        return pwd.getpwnam(username)
    except KeyError:
        return None


def _lookup_passwd_uid(uid: int) -> pwd.struct_passwd | None:
    try:
        return pwd.getpwuid(uid)
    except KeyError:
        return None


def resolve_user_session(env: Mapping[str, str] | None = None) -> UserSessionContext:
    """Resolve the active SteamOS user session across direct, sudo, and Decky root hosts."""
    environ = env if env is not None else os.environ
    euid = os.geteuid()
    is_root_host = euid == 0

    candidates: list[str] = [
        str(environ.get("DECKY_USER", "")).strip(),
        str(environ.get("SUDO_USER", "")).strip(),
    ]
    if not is_root_host:
        candidates.append(str(environ.get("USER", "")).strip())

    pw: pwd.struct_passwd | None = None
    for cand in candidates:
        pw = _lookup_passwd_name(cand)
        if pw is not None:
            break

    if pw is None and not is_root_host:
        pw = _lookup_passwd_uid(euid)

    if pw is None:
        pw_1000 = _lookup_passwd_uid(1000)
        if pw_1000 is not None and pw_1000.pw_uid != 0:
            pw = pw_1000
    if pw is None:
        pw = _lookup_passwd_name("deck")
    if pw is None:
        pw = _lookup_passwd_uid(euid)

    if pw is not None:
        uid = pw.pw_uid
        gid = pw.pw_gid
        username = pw.pw_name
        default_home = Path(pw.pw_dir)
    else:
        uid = euid
        gid = os.getegid()
        username = str(environ.get("USER") or "deck")
        default_home = Path.home()

    override_home = str(environ.get("DECKY_USER_HOME", "")).strip()
    home_dir = Path(override_home) if override_home else default_home

    xdg_runtime = str(environ.get("XDG_RUNTIME_DIR", "")).strip()
    if not is_root_host and xdg_runtime:
        runtime_dir = Path(xdg_runtime)
    else:
        runtime_dir = Path(f"/run/user/{uid}")

    return UserSessionContext(
        uid=uid,
        gid=gid,
        username=username,
        home_dir=home_dir,
        runtime_dir=runtime_dir,
        is_root_host=is_root_host,
    )
