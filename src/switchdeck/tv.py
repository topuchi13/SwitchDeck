"""Universal TV power & HDMI input bridge (CEC, Samsung Tizen, LG webOS, Sony Bravia, Roku, WoL, Webhooks)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Protocol

from .domain import TvDriverConfig
from .security import (
    validate_hdmi_input,
    validate_host,
    validate_port,
    validate_tv_secret,
    validate_webhook_url,
)

LOG = logging.getLogger("switchdeck.tv")
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_WS_HANDSHAKE_BYTES = 16384
MAX_WS_PAYLOAD_BYTES = 65536


class _WsPayloadTooLarge(ConnectionError, ValueError):
    """Raised when an incoming WebSocket frame exceeds MAX_WS_PAYLOAD_BYTES."""


class TvDriver(Protocol):
    """Unified interface for waking a TV and switching HDMI inputs."""

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        ...


def send_wake_on_lan(mac_address: str, broadcast_ip: str = "255.255.255.255", port: int = 9) -> bool:
    """Send a standard 102-byte UDP Wake-on-LAN magic packet."""
    cleaned = "".join(ch for ch in mac_address if ch in "0123456789abcdefABCDEF")
    if len(cleaned) != 12:
        return False
    mac_bytes = bytes.fromhex(cleaned)
    magic = b"\xff" * 6 + mac_bytes * 16
    try:
        host = validate_host(broadcast_ip)
        valid_port = validate_port(port)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(magic, (host, valid_port))
        return True
    except (OSError, ValueError):
        return False


def _ws_encode_frame(opcode: int, data: bytes) -> bytes:
    """Encode a masked RFC 6455 client frame."""
    mask = os.urandom(4)
    header = bytearray([0x80 | (opcode & 0x0F)])
    length = len(data)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    return bytes(header) + masked


def _ws_encode_text_frame(payload: str) -> bytes:
    """Encode a masked RFC 6455 client text frame."""
    return _ws_encode_frame(0x1, payload.encode("utf-8"))


def _ws_encode_pong_frame(payload: bytes = b"") -> bytes:
    """Encode a masked RFC 6455 client Pong frame (0x8A)."""
    return _ws_encode_frame(0xA, payload[:125])


def _recv_exact(sock: socket.socket, count: int) -> bytes:
    """Read exactly `count` bytes from a socket or return empty/partial on EOF."""
    buf = bytearray()
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    return bytes(buf)


def _ws_read_text_frame(sock: socket.socket) -> str | None:
    """Read a single RFC 6455 server text frame, replying to Ping control frames."""
    for _ in range(32):
        first_two = _recv_exact(sock, 2)
        if len(first_two) < 2:
            return None
        opcode = first_two[0] & 0x0F
        masked = bool(first_two[1] & 0x80)
        length = first_two[1] & 0x7F
        if length == 126:
            ext = _recv_exact(sock, 2)
            if len(ext) < 2:
                return None
            length = struct.unpack("!H", ext)[0]
        elif length == 127:
            ext = _recv_exact(sock, 8)
            if len(ext) < 8:
                return None
            length = struct.unpack("!Q", ext)[0]
        if length > MAX_WS_PAYLOAD_BYTES:
            raise _WsPayloadTooLarge(
                f"WebSocket payload length {length} exceeds {MAX_WS_PAYLOAD_BYTES} bytes"
            )
        mask_key = _recv_exact(sock, 4) if masked else b""
        if masked and len(mask_key) < 4:
            return None
        buf = _recv_exact(sock, length)
        if len(buf) < length or opcode == 0x8:  # Incomplete or Close
            return None
        if masked:
            buf = bytes(b ^ mask_key[i % 4] for i, b in enumerate(buf))
        if opcode == 0x9:  # Ping -> reply Pong (0x8A masked) and read next frame
            sock.sendall(_ws_encode_pong_frame(buf))
            continue
        if opcode == 0xA:  # Unsolicited Pong -> read next frame
            continue
        return buf.decode("utf-8", errors="replace")
    raise ConnectionError("Too many consecutive WebSocket control frames")


class CecTvDriver:
    """Hardware HDMI-CEC via steamos-manager HdmiCec1 + optional cec-ctl."""

    def __init__(self, cec_trigger: Callable[[], bool]) -> None:
        self._cec_trigger = cec_trigger

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.auto_power_on and not config.auto_switch_input:
            return False
        return self._cec_trigger()


class _WsTlsClientMixin:
    """Shared RFC 6455 WebSocket + TOFU SHA-256 TLS client primitives."""

    _custom_ssl_context: ssl.SSLContext | None
    _timeout: float
    _get_cert_fingerprint: Callable[[str], str] | None
    _set_cert_fingerprint: Callable[[str, str], None] | None

    def _build_ssl_context(self) -> ssl.SSLContext:
        if self._custom_ssl_context is not None:
            return self._custom_ssl_context
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _verify_tofu_fingerprint(self, sock: socket.socket, host: str, trust_new_cert: bool) -> None:
        if not hasattr(sock, "getpeercert"):
            return
        cert_der = sock.getpeercert(binary_form=True)
        if not cert_der:
            return
        fp = hashlib.sha256(cert_der).hexdigest().lower()
        pinned = self._get_cert_fingerprint(host).strip().lower() if self._get_cert_fingerprint else ""
        if pinned and not trust_new_cert:
            if fp != pinned:
                sock.close()
                raise ssl.SSLCertVerificationError(
                    f"TV TLS fingerprint mismatch for {host} (use --trust-new-cert / re-pair to rotate)"
                )
        elif self._set_cert_fingerprint is not None and (not pinned or trust_new_cert):
            self._set_cert_fingerprint(host, fp)

    def _open_ws_socket(
        self,
        host: str,
        port: int,
        path: str,
        *,
        use_tls: bool,
        trust_new_cert: bool = False,
        timeout: float | None = None,
    ) -> socket.socket:
        effective_timeout = self._timeout if timeout is None else timeout
        raw_sock = socket.create_connection((host, port), timeout=effective_timeout)
        sock: socket.socket = raw_sock
        try:
            if use_tls:
                ctx = self._build_ssl_context()
                sock = ctx.wrap_socket(raw_sock, server_hostname=host)
                self._verify_tofu_fingerprint(sock, host, trust_new_cert=trust_new_cert)

            sock.settimeout(effective_timeout)
            host_hdr = f"[{host}]" if ":" in host else host
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host_hdr}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
            sock.sendall(req)

            # Read headers byte-by-byte up to \r\n\r\n so an immediately following
            # WebSocket greeting frame is never consumed into the handshake buffer.
            raw_response = bytearray()
            while b"\r\n\r\n" not in raw_response:
                if len(raw_response) >= MAX_WS_HANDSHAKE_BYTES:
                    raise ConnectionError("WebSocket upgrade response exceeded 16384 bytes")
                chunk = sock.recv(1)
                if not chunk:
                    break
                raw_response.extend(chunk)
            response = bytes(raw_response)
            if b"\r\n\r\n" not in response:
                raise ConnectionError(f"WebSocket upgrade incomplete: {response[:120]!r}")

            header_block = response.split(b"\r\n\r\n", 1)[0]
            if b"101 " not in header_block.split(b"\r\n", 1)[0]:
                raise ConnectionError(f"WebSocket upgrade rejected: {response[:120]!r}")

            expected_accept = base64.b64encode(
                hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
            ).decode("ascii")
            if expected_accept.encode("ascii") not in header_block:
                raise ConnectionError("Invalid Sec-WebSocket-Accept header")
            return sock
        except Exception:
            try:
                sock.close()
            except OSError:
                pass
            raise


class SamsungTizenDriver(_WsTlsClientMixin):
    """Samsung Tizen SmartView WebSocket controller (S90C / 2016+ Tizen TVs).

    Connects over port 8002 (WSS with TOFU SHA-256 certificate pinning) or 8001 (WS),
    saves the pairing token returned in `ms.channel.connect`, and optionally sends
    Wake-on-LAN before connecting.
    """

    def __init__(
        self,
        get_token: Callable[[str], str],
        set_token: Callable[[str, str], None],
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = 3.0,
        get_cert_fingerprint: Callable[[str], str] | None = None,
        set_cert_fingerprint: Callable[[str, str], None] | None = None,
    ) -> None:
        self._get_token = get_token
        self._set_token = set_token
        self._custom_ssl_context = ssl_context
        self._timeout = timeout
        self._get_cert_fingerprint = get_cert_fingerprint
        self._set_cert_fingerprint = set_cert_fingerprint

    def _connect_ws(
        self,
        host: str,
        port: int,
        token: str,
        trust_new_cert: bool = False,
    ) -> socket.socket:
        host = validate_host(host)
        port = validate_port(port)

        app_name = base64.b64encode(b"SwitchDeck").decode("ascii")
        path = f"/api/v2/channels/samsung.remote.control?name={app_name}"
        if token:
            path += f"&token={urllib.parse.quote(str(token), safe='')}"

        use_tls = (port == 8002) or (self._custom_ssl_context is not None and port != 8001)
        return self._open_ws_socket(
            host=host,
            port=port,
            path=path,
            use_tls=use_tls,
            trust_new_cert=trust_new_cert,
        )

    def send_key(
        self,
        host: str,
        port: int,
        key_name: str,
        trust_new_cert: bool = False,
    ) -> str:
        """Connect, capture/refresh token if issued, send remote key, and return token."""
        host = validate_host(host)
        port = validate_port(port)
        token = self._get_token(host)
        with self._connect_ws(host, port, token, trust_new_cert=trust_new_cert) as sock:
            greeting = _ws_read_text_frame(sock)
            if greeting:
                try:
                    msg = json.loads(greeting)
                    new_token = (msg.get("data") or {}).get("token")
                    if new_token and str(new_token) != token:
                        token = str(new_token)
                        self._set_token(host, token)
                except ValueError:
                    pass

            cmd = json.dumps(
                {
                    "method": "ms.remote.control",
                    "params": {
                        "Cmd": "Click",
                        "DataOfCmd": key_name,
                        "Option": "false",
                        "TypeOfRemote": "SendRemoteKey",
                    },
                }
            )
            sock.sendall(_ws_encode_text_frame(cmd))
        return token

    def pair(self, host: str, port: int = 8002, trust_new_cert: bool = False) -> str:
        """Initiate pairing (triggers on-TV Allow popup) and persist issued token."""
        return self.send_key(host, port, "KEY_HOME", trust_new_cert=trust_new_cert)

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.host:
            return False
        host = validate_host(config.host)
        port = validate_port(config.port or 8002)
        if config.auto_power_on and config.mac_address:
            send_wake_on_lan(config.mac_address)
        try:
            if config.auto_power_on:
                self.send_key(host, port, "KEY_POWERON")
            if config.auto_switch_input:
                self.send_key(host, port, "KEY_HDMI")
            return True
        except OSError as exc:
            LOG.warning("Samsung TV wake/switch failed for %s:%s: %s", host, port, exc)
            return False


class LgWebOsDriver(_WsTlsClientMixin):
    """LG webOS SSAP WebSocket controller (OLED C/G/B series, ports 3001 WSS / 3000 WS)."""

    _PERMISSIONS: tuple[str, ...] = (
        "LAUNCH",
        "LAUNCH_WEBAPP",
        "CONTROL_INPUT_TV",
        "CONTROL_POWER",
        "READ_INSTALLED_APPS",
        "READ_INPUT_DEVICE_LIST",
        "READ_CURRENT_CHANNEL",
        "READ_RUNNING_APPS",
    )

    def __init__(
        self,
        get_token: Callable[[str], str],
        set_token: Callable[[str, str], None],
        ssl_context: ssl.SSLContext | None = None,
        timeout: float = 3.0,
        pairing_timeout: float = 15.0,
        wol_retry_delay: float = 0.6,
        get_cert_fingerprint: Callable[[str], str] | None = None,
        set_cert_fingerprint: Callable[[str, str], None] | None = None,
    ) -> None:
        self._get_token = get_token
        self._set_token = set_token
        self._custom_ssl_context = ssl_context
        self._timeout = timeout
        self._pairing_timeout = pairing_timeout
        self._wol_retry_delay = wol_retry_delay
        self._get_cert_fingerprint = get_cert_fingerprint
        self._set_cert_fingerprint = set_cert_fingerprint

    def _connect_ssap(
        self,
        host: str,
        port: int,
        *,
        trust_new_cert: bool = False,
    ) -> tuple[socket.socket, int]:
        requested_port = validate_port(port or 3001)
        use_tls = not (requested_port == 3000 and self._custom_ssl_context is None)
        try:
            sock = self._open_ws_socket(
                host=host,
                port=requested_port,
                path="/",
                use_tls=use_tls,
                trust_new_cert=trust_new_cert,
            )
            return sock, requested_port
        except ConnectionRefusedError:
            has_pinned_cert = bool(
                self._get_cert_fingerprint and self._get_cert_fingerprint(host).strip()
            )
            if (
                requested_port == 3001
                and self._custom_ssl_context is None
                and not has_pinned_cert
            ):
                sock = self._open_ws_socket(
                    host=host,
                    port=3000,
                    path="/",
                    use_tls=False,
                    trust_new_cert=trust_new_cert,
                )
                return sock, 3000
            raise

    def _register_ssap(
        self,
        sock: socket.socket,
        host: str,
        *,
        wait_for_prompt: bool,
    ) -> str:
        token = self._get_token(host)
        reg_payload: dict[str, Any] = {
            "forcePairing": False,
            "pairingType": "PROMPT",
            "manifest": {
                "manifestVersion": 1,
                "appVersion": "1.1",
                "permissions": list(self._PERMISSIONS),
            },
        }
        if token:
            reg_payload["client-key"] = token
        reg_msg = json.dumps({"id": "register_0", "type": "register", "payload": reg_payload})
        sock.sendall(_ws_encode_text_frame(reg_msg))

        for _ in range(8):
            try:
                frame = _ws_read_text_frame(sock)
            except TimeoutError as exc:
                if wait_for_prompt:
                    raise TimeoutError("Accept the pairing prompt on your LG TV and try again") from exc
                raise
            if frame is None:
                raise ConnectionError("LG webOS connection closed during registration")
            try:
                msg = json.loads(frame)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue

            msg_type = str(msg.get("type") or "").lower()
            payload = msg.get("payload") if isinstance(msg.get("payload"), dict) else {}
            if msg_type == "registered":
                new_key = str(payload.get("client-key") or "").strip()
                if new_key and new_key != token:
                    token = new_key
                    self._set_token(host, token)
                return token
            if msg_type == "response" and str(payload.get("pairingType") or "").upper() == "PROMPT":
                if not wait_for_prompt:
                    raise PermissionError("LG webOS TV requires pairing")
                sock.settimeout(self._pairing_timeout)
                continue
            if msg_type == "error":
                raise ConnectionError(f"LG webOS registration error: {msg.get('error')}")

        raise ConnectionError("LG webOS registration did not complete")

    @staticmethod
    def _send_ssap_request(
        sock: socket.socket,
        req_id: str,
        uri: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        req_msg = json.dumps(
            {
                "id": req_id,
                "type": "request",
                "uri": uri,
                "payload": payload,
            }
        )
        sock.sendall(_ws_encode_text_frame(req_msg))
        try:
            frame = _ws_read_text_frame(sock)
        except OSError:
            return None
        if not frame:
            return None
        try:
            parsed = json.loads(frame)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _map_hdmi_targets(hdmi_input: str) -> tuple[str | None, str]:
        hdmi = validate_hdmi_input(hdmi_input or "HDMI2")
        if hdmi.startswith("HDMI"):
            idx = hdmi[4:]
            return f"HDMI_{idx}", f"com.webos.app.hdmi{idx}"
        if hdmi == "AV1":
            return "AV_1", "com.webos.app.externalinput.av1"
        return None, "com.webos.app.livetv"

    def pair_with_port(
        self,
        host: str,
        port: int = 3001,
        trust_new_cert: bool = False,
    ) -> tuple[str, int]:
        """Pair with an LG webOS TV (waiting for the on-TV PROMPT) and return (client_key, port)."""
        clean_host = validate_host(host)
        sock, actual_port = self._connect_ssap(
            clean_host,
            port or 3001,
            trust_new_cert=trust_new_cert,
        )
        with sock:
            token = self._register_ssap(sock, clean_host, wait_for_prompt=True)
        return token, actual_port

    def pair(self, host: str, port: int = 3001, trust_new_cert: bool = False) -> str:
        """Initiate pairing with an LG webOS TV and persist the issued client-key."""
        token, _ = self.pair_with_port(host, port=port, trust_new_cert=trust_new_cert)
        return token

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.host or (not config.auto_power_on and not config.auto_switch_input):
            return False
        host = validate_host(config.host)
        port = validate_port(config.port or 3001)
        has_wol = bool(config.auto_power_on and config.mac_address)
        if has_wol:
            send_wake_on_lan(config.mac_address)

        attempts = 3 if has_wol else 1
        try:
            sock: socket.socket | None = None
            for attempt in range(attempts):
                try:
                    sock, _ = self._connect_ssap(host, port, trust_new_cert=False)
                    break
                except (ssl.SSLError, PermissionError):
                    raise
                except OSError:
                    if attempt + 1 >= attempts:
                        raise
                    if self._wol_retry_delay > 0:
                        time.sleep(self._wol_retry_delay)

            assert sock is not None
            with sock:
                self._register_ssap(sock, host, wait_for_prompt=False)
                if config.auto_power_on:
                    self._send_ssap_request(sock, "screen_on_1", "ssap://system/turnOnScreen", {})
                if config.auto_switch_input:
                    input_id, app_id = self._map_hdmi_targets(config.hdmi_input or "HDMI2")
                    switched = False
                    if input_id is not None:
                        resp = self._send_ssap_request(
                            sock,
                            "switch_input_2",
                            "ssap://tv/switchInput",
                            {"inputId": input_id},
                        )
                        if resp is not None:
                            resp_type = str(resp.get("type") or "").lower()
                            resp_payload = (
                                resp.get("payload") if isinstance(resp.get("payload"), dict) else {}
                            )
                            switched = (
                                resp_type != "error" and resp_payload.get("returnValue") is not False
                            )
                        else:
                            switched = True
                    if not switched:
                        self._send_ssap_request(
                            sock,
                            "launch_input_3",
                            "ssap://system.launcher/launch",
                            {"id": app_id},
                        )
            return True
        except (OSError, ConnectionError, ValueError) as exc:
            LOG.warning("LG webOS wake/switch failed for %s:%s: %s", host, port, exc)
            return False


class SonyBraviaDriver:
    """Sony Bravia LAN REST controller (/sony/system & /sony/avContent via X-Auth-PSK)."""

    _ALLOWED_SERVICES: frozenset[str] = frozenset({"system", "avContent"})

    def __init__(
        self,
        get_psk: Callable[[str], str],
        set_psk: Callable[[str, str], None] | None = None,
        timeout: float = 2.5,
        wake_delay: float = 0.4,
    ) -> None:
        self._get_psk = get_psk
        self._set_psk = set_psk
        self._timeout = timeout
        self._wake_delay = wake_delay

    def _rpc(
        self,
        host: str,
        port: int,
        psk: str,
        service: str,
        method: str,
        params: list[Any],
        version: str = "1.0",
    ) -> dict[str, Any]:
        clean_host = validate_host(host)
        clean_port = validate_port(port or 80)
        if not psk or not psk.strip():
            raise PermissionError("Sony Bravia Pre-Shared Key (PSK) not configured")
        clean_psk = validate_tv_secret(psk)
        if service not in self._ALLOWED_SERVICES:
            raise ValueError(f"Unsupported Sony Bravia service: {service!r}")

        host_url = f"[{clean_host}]" if ":" in clean_host else clean_host
        port_suffix = "" if clean_port == 80 else f":{clean_port}"
        url = f"http://{host_url}{port_suffix}/sony/{service}"
        body = json.dumps(
            {"method": method, "id": 1, "params": params, "version": version}
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Auth-PSK": clean_psk,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read(MAX_WS_PAYLOAD_BYTES)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise PermissionError(
                    f"Sony Bravia rejected Pre-Shared Key (HTTP {exc.code})"
                ) from exc
            raise
        data = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(data, dict) and data.get("error"):
            raise ConnectionError(f"Sony Bravia RPC error: {data['error']}")
        return data if isinstance(data, dict) else {}

    def pair(self, host: str, port: int = 80, psk: str = "") -> str:
        """Verify Sony Bravia X-Auth-PSK with getPowerStatus and persist the secret."""
        clean_host = validate_host(host)
        clean_port = validate_port(port or 80)
        raw_secret = psk if (psk and psk.strip()) else self._get_psk(clean_host)
        if not raw_secret or not raw_secret.strip():
            raise PermissionError("Sony Bravia Pre-Shared Key (PSK) is required")
        effective_psk = validate_tv_secret(raw_secret)
        self._rpc(clean_host, clean_port, effective_psk, "system", "getPowerStatus", [])
        if self._set_psk is not None:
            self._set_psk(clean_host, effective_psk)
        return effective_psk

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.host or (not config.auto_power_on and not config.auto_switch_input):
            return False
        host = validate_host(config.host)
        port = validate_port(config.port or 80)
        if config.auto_power_on and config.mac_address:
            send_wake_on_lan(config.mac_address)
        psk = self._get_psk(host)
        if not psk:
            LOG.warning("Sony Bravia PSK missing for %s:%s", host, port)
            return False

        woke_tv = False
        try:
            if config.auto_power_on:
                self._rpc(host, port, psk, "system", "setPowerStatus", [{"status": True}])
                woke_tv = True
            if config.auto_switch_input and config.hdmi_input:
                hdmi = validate_hdmi_input(config.hdmi_input)
                uri = ""
                if hdmi.startswith("HDMI"):
                    uri = f"extInput:hdmi?port={hdmi[4:]}"
                elif hdmi == "AV1":
                    uri = "extInput:composite?port=1"
                if uri:
                    try:
                        self._rpc(host, port, psk, "avContent", "setPlayContent", [{"uri": uri}])
                    except PermissionError:
                        raise
                    except (OSError, urllib.error.URLError):
                        if not woke_tv:
                            raise
                        if self._wake_delay > 0:
                            time.sleep(self._wake_delay)
                        self._rpc(host, port, psk, "avContent", "setPlayContent", [{"uri": uri}])
            return True
        except (OSError, urllib.error.URLError, ValueError) as exc:
            LOG.warning("Sony Bravia wake/switch failed for %s:%s: %s", host, port, exc)
            return False


class RokuEcpDriver:
    """Roku TV ECP HTTP controller (default :8060, optional Wake-on-LAN)."""

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.host:
            return False
        host = validate_host(config.host)
        port = validate_port(config.port or 8060)
        host_url = f"[{host}]" if ":" in host else host
        if config.auto_power_on and config.mac_address:
            send_wake_on_lan(config.mac_address)
        hdmi = validate_hdmi_input(config.hdmi_input) if config.hdmi_input else ""
        actions = []
        if config.auto_power_on:
            actions.append("PowerOn")
        if config.auto_switch_input and hdmi:
            actions.append(f"Input{hdmi}")
        if not actions:
            return False
        ok = True
        for key in actions:
            req = urllib.request.Request(
                f"http://{host_url}:{port}/keypress/{key}",
                data=b"",
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=2.0):
                    pass
            except (urllib.error.URLError, OSError):
                ok = False
        return ok


class WakeOnLanTvDriver:
    """Standalone UDP Wake-on-LAN controller for any Smart TV with WoL enabled."""

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.auto_power_on or not config.mac_address:
            return False
        broadcast = config.host.strip() or "255.255.255.255"
        return send_wake_on_lan(config.mac_address, broadcast_ip=broadcast, port=config.port or 9)


class WebhookTvDriver:
    """Generic Home Assistant / IR-blaster / custom HTTP webhook driver."""

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.webhook_url:
            return False
        url = validate_webhook_url(config.webhook_url)
        hdmi = validate_hdmi_input(config.hdmi_input) if config.hdmi_input else ""
        payload = json.dumps(
            {
                "event": "switchdeck_docked",
                "hdmi_input": hdmi,
                "auto_power_on": config.auto_power_on,
                "auto_switch_input": config.auto_switch_input,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=2.5):
                return True
        except (urllib.error.URLError, OSError):
            return False


def create_tv_driver(
    driver_name: str,
    cec_trigger: Callable[[], bool],
    get_token: Callable[[str], str],
    set_token: Callable[[str, str], None],
    get_cert_fingerprint: Callable[[str], str] | None = None,
    set_cert_fingerprint: Callable[[str, str], None] | None = None,
    get_driver_token: Callable[[str, str], str] | None = None,
    set_driver_token: Callable[[str, str], None] | None = None,
) -> TvDriver | None:
    """Factory resolving configured TV control backend."""
    name = (driver_name or "none").lower()
    _get = get_driver_token or (lambda _drv, host: get_token(host))
    _set = set_driver_token or (lambda _drv, host, tok: set_token(host, tok))

    if name == "cec":
        return CecTvDriver(cec_trigger)
    if name == "samsung_tizen":
        return SamsungTizenDriver(
            get_token=lambda h: _get("samsung_tizen", h),
            set_token=lambda h, t: _set("samsung_tizen", h, t),
            get_cert_fingerprint=get_cert_fingerprint,
            set_cert_fingerprint=set_cert_fingerprint,
        )
    if name == "lg_webos":
        return LgWebOsDriver(
            get_token=lambda h: _get("lg_webos", h),
            set_token=lambda h, t: _set("lg_webos", h, t),
            get_cert_fingerprint=get_cert_fingerprint,
            set_cert_fingerprint=set_cert_fingerprint,
        )
    if name == "sony_bravia":
        return SonyBraviaDriver(
            get_psk=lambda h: _get("sony_bravia", h),
            set_psk=lambda h, t: _set("sony_bravia", h, t),
        )
    if name == "roku_ecp":
        return RokuEcpDriver()
    if name == "wol":
        return WakeOnLanTvDriver()
    if name == "webhook":
        return WebhookTvDriver()
    return None
