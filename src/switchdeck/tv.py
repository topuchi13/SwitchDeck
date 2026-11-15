"""Universal TV power & HDMI input bridge (CEC, Samsung Tizen WSS, Roku, Webhooks)."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import socket
import ssl
import struct
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Protocol

from .domain import TvDriverConfig
from .security import validate_hdmi_input, validate_host, validate_port, validate_webhook_url

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


class SamsungTizenDriver:
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
                    "Samsung TV TLS fingerprint mismatch (use --trust-new-cert / re-pair to rotate)"
                )
        elif self._set_cert_fingerprint is not None and (not pinned or trust_new_cert):
            self._set_cert_fingerprint(host, fp)

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

        raw_sock = socket.create_connection((host, port), timeout=self._timeout)
        sock: socket.socket = raw_sock
        try:
            use_tls = (port == 8002) or (self._custom_ssl_context is not None and port != 8001)
            if use_tls:
                ctx = self._build_ssl_context()
                sock = ctx.wrap_socket(raw_sock, server_hostname=host)
                self._verify_tofu_fingerprint(sock, host, trust_new_cert=trust_new_cert)

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
                    raise ConnectionError("Samsung WebSocket upgrade response exceeded 16384 bytes")
                chunk = sock.recv(1)
                if not chunk:
                    break
                raw_response.extend(chunk)
            response = bytes(raw_response)
            if b"\r\n\r\n" not in response:
                raise ConnectionError(f"Samsung WebSocket upgrade incomplete: {response[:120]!r}")

            header_block = response.split(b"\r\n\r\n", 1)[0]
            if b"101 " not in header_block.split(b"\r\n", 1)[0]:
                raise ConnectionError(f"Samsung WebSocket upgrade rejected: {response[:120]!r}")

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


class RokuEcpDriver:
    """Roku TV ECP HTTP controller (:8060)."""

    def wake_and_switch(self, config: TvDriverConfig) -> bool:
        if not config.host:
            return False
        host = validate_host(config.host)
        host_url = f"[{host}]" if ":" in host else host
        hdmi = validate_hdmi_input(config.hdmi_input) if config.hdmi_input else ""
        actions = []
        if config.auto_power_on:
            actions.append("PowerOn")
        if config.auto_switch_input and hdmi:
            actions.append(f"Input{hdmi}")
        ok = True
        for key in actions:
            req = urllib.request.Request(
                f"http://{host_url}:8060/keypress/{key}",
                data=b"",
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=2.0):
                    pass
            except (urllib.error.URLError, OSError):
                ok = False
        return ok


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
) -> TvDriver | None:
    """Factory resolving configured TV control backend."""
    name = (driver_name or "none").lower()
    if name == "cec":
        return CecTvDriver(cec_trigger)
    if name == "samsung_tizen":
        return SamsungTizenDriver(
            get_token=get_token,
            set_token=set_token,
            get_cert_fingerprint=get_cert_fingerprint,
            set_cert_fingerprint=set_cert_fingerprint,
        )
    if name == "roku_ecp":
        return RokuEcpDriver()
    if name == "webhook":
        return WebhookTvDriver()
    return None
