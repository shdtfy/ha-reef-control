"""TC420 / SIMU-LUX USB bridge for Reef Control v0.3.0.

The bridge reads the four desired SEA WATER light channel values from the
Reef Control Home Assistant integration and keeps the TC420 fast-play session
alive over USB. TC420 channel 5 is intentionally kept at 0%.

Stored TC420 programs are never modified.
"""

from __future__ import annotations

import json
import os
import signal
import struct
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import usb.core
import usb.util

APP_VERSION = "0.3.0"
VENDOR_ID = 0x0888
PRODUCT_ID = 0x4000
INTERFACE = 0
PACKET_SIZE = 64
USB_TIMEOUT_MS = 5000
USB_RETRIES = 3
USB_SETTLE_SECONDS = 0.5
USB_RETRY_DELAY_SECONDS = 0.8
LIVE_KEEPALIVE_SECONDS = 0.4
USB_RECONNECT_SECONDS = 2.0
CMD_TIME_SYNC = 0x11
CMD_PLAY_INIT = 0x15
CMD_PLAY_SET_CHANNELS = 0x16
OPTIONS_PATH = Path("/data/options.json")
STATE_PATH = Path("/data/tc420_state.json")
HA_BRIDGE_URL = "http://supervisor/core/api/reef_control/tc420/bridge"
HA_REQUEST_TIMEOUT = 2.0
HA_STALE_SECONDS = 10.0
STATUS_POST_SECONDS = 5.0
_running = True


def log(level: str, message: str) -> None:
    print(f"[{level}] {message}", flush=True)


def _stop(signum, frame) -> None:  # noqa: ARG001
    global _running
    _running = False


def _as_int(data: dict, key: str, default: int) -> int:
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return default


def read_options() -> dict:
    try:
        data = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {
        "bridge_enabled": bool(data.get("bridge_enabled", False)),
        "ha_poll_interval": max(1, min(10, _as_int(data, "ha_poll_interval", 1))),
        "sync_time_on_connect": bool(data.get("sync_time_on_connect", False)),
        "poll_interval": max(2, min(60, _as_int(data, "poll_interval", 5))),
        "live_test_token": max(0, _as_int(data, "live_test_token", 0)),
        "live_test_channel": max(1, min(4, _as_int(data, "live_test_channel", 1))),
        "live_test_level": max(0, min(20, _as_int(data, "live_test_level", 10))),
        "live_test_seconds": max(1, min(5, _as_int(data, "live_test_seconds", 3))),
    }


def read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def find_controller():
    return usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)


def build_packet(command: int, data: bytes = b"") -> bytes:
    if len(data) > 56:
        raise ValueError("TC420 payload is too large")
    packet = bytearray(PACKET_SIZE)
    packet[0:2] = b"\x55\xaa"
    packet[2] = command & 0xFF
    struct.pack_into("!H", packet, 3, len(data))
    packet[5 : 5 + len(data)] = data
    packet[61] = sum(packet[:61]) & 0xFF
    packet[62:64] = b"\x0d\x0a"
    return bytes(packet)


def build_time_sync_packet(now: datetime | None = None) -> bytes:
    now = now or datetime.now()
    return build_packet(
        CMD_TIME_SYNC,
        struct.pack("!HBBBBB", now.year, now.month, now.day, now.hour, now.minute, now.second),
    )


def build_play_init_packet(name: str = "REEFCTRL") -> bytes:
    name_bytes = name.encode("ascii", errors="replace")[:8] or b"REEFCTRL"
    return build_packet(CMD_PLAY_INIT, name_bytes + struct.pack("!H", 0x007F))


def build_play_channels_packet(values: list[int]) -> bytes:
    if len(values) != 5:
        raise ValueError("Exactly five TC420 channel values are required")
    safe = [max(0, min(100, int(v))) for v in values]
    return build_packet(CMD_PLAY_SET_CHANNELS, bytes([0xF5, *safe, 0x00]))


def open_device(device):
    detached = False
    try:
        if device.is_kernel_driver_active(INTERFACE):
            device.detach_kernel_driver(INTERFACE)
            detached = True
            log("INFO", "Detached kernel HID driver from interface 0.")
    except (NotImplementedError, usb.core.USBError) as err:
        log("WARNING", f"Could not query/detach kernel HID driver: {err}")

    interface = device[0][(INTERFACE, 0)]
    try:
        in_ep = interface[0]
        out_ep = interface[1]
    except (IndexError, TypeError) as err:
        raise RuntimeError("TC420 interface does not expose the expected two endpoints") from err

    if usb.util.endpoint_direction(in_ep.bEndpointAddress) != usb.util.ENDPOINT_IN:
        raise RuntimeError("Unexpected TC420 endpoint layout: endpoint 0 is not IN")
    if usb.util.endpoint_direction(out_ep.bEndpointAddress) != usb.util.ENDPOINT_OUT:
        raise RuntimeError("Unexpected TC420 endpoint layout: endpoint 1 is not OUT")

    log("INFO", f"TC420 endpoints ready: IN=0x{int(in_ep.bEndpointAddress):02x}, OUT=0x{int(out_ep.bEndpointAddress):02x}")
    time.sleep(USB_SETTLE_SECONDS)
    return in_ep, out_ep, detached


def close_device(device, detached: bool) -> None:
    if device is None:
        return
    usb.util.dispose_resources(device)
    if detached:
        try:
            device.attach_kernel_driver(INTERFACE)
            log("INFO", "Reattached kernel HID driver to interface 0.")
        except (NotImplementedError, usb.core.USBError) as err:
            log("WARNING", f"Could not reattach kernel HID driver: {err}")


def parse_ack(response: bytes, label: str) -> None:
    if len(response) < 6:
        raise RuntimeError(f"{label}: short TC420 response ({len(response)} bytes)")
    data_len = int.from_bytes(response[3:5], byteorder="big")
    status = response[5] if data_len >= 1 else None
    if data_len != 1 or status != 0x00:
        raise RuntimeError(f"{label}: controller did not acknowledge (data_len={data_len}, status={status!r})")


def send_and_expect_ok(in_ep, out_ep, packet: bytes, label: str) -> None:
    last_error: Exception | None = None
    for attempt in range(1, USB_RETRIES + 1):
        try:
            written = out_ep.write(packet, timeout=USB_TIMEOUT_MS)
            if written != PACKET_SIZE:
                raise RuntimeError(f"{label}: wrote {written}/{PACKET_SIZE} bytes")
            response = bytes(in_ep.read(PACKET_SIZE, timeout=USB_TIMEOUT_MS))
            parse_ack(response, label)
            if attempt > 1:
                log("INFO", f"{label}: succeeded on retry {attempt}/{USB_RETRIES}.")
            return
        except (usb.core.USBTimeoutError, usb.core.USBError, RuntimeError) as err:
            last_error = err
            if attempt < USB_RETRIES:
                log("WARNING", f"{label}: attempt {attempt}/{USB_RETRIES} failed: {err}; retrying...")
                time.sleep(USB_RETRY_DELAY_SECONDS)
    raise RuntimeError(f"{label}: failed after {USB_RETRIES} attempts: {last_error}")


def synchronize_clock(device) -> bool:
    detached = False
    try:
        in_ep, out_ep, detached = open_device(device)
        now = datetime.now()
        send_and_expect_ok(in_ep, out_ep, build_time_sync_packet(now), "Clock sync")
        log("INFO", f"TC420 clock synchronization successful: {now:%Y-%m-%d %H:%M:%S}")
        return True
    except Exception as err:
        log("WARNING", f"TC420 clock synchronization skipped after retries: {err}")
        return False
    finally:
        close_device(device, detached)


class SharedBridgeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.entry_id: str | None = None
        self.channels = [0, 0, 0, 0]
        self.last_ha_ok = 0.0
        self.usb_connected = False
        self.status = "starting"
        self.last_error: str | None = None

    def update_desired(self, entry_id: str, channels: list[int]) -> None:
        with self._lock:
            self.entry_id = entry_id
            self.channels = list(channels[:4])
            self.last_ha_ok = time.monotonic()

    def get_desired(self) -> tuple[list[int], float]:
        with self._lock:
            return list(self.channels), self.last_ha_ok

    def set_usb_status(self, connected: bool, status: str, last_error: str | None = None) -> None:
        with self._lock:
            self.usb_connected = connected
            self.status = status
            self.last_error = last_error

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "entry_id": self.entry_id,
                "connected": self.usb_connected,
                "status": self.status,
                "last_error": self.last_error,
                "active_channels": list(self.channels),
            }


def _ha_request(token: str, method: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        HA_BRIDGE_URL,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=HA_REQUEST_TIMEOUT) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8")) if raw else {}


def home_assistant_worker(shared: SharedBridgeState, poll_interval: int) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN", "").strip()
    if not token:
        shared.set_usb_status(False, "home_assistant_api_unavailable", "SUPERVISOR_TOKEN is missing")
        log("ERROR", "SUPERVISOR_TOKEN is missing. Check homeassistant_api: true in app config.yaml.")
        return

    next_status_post = 0.0
    last_fetch_error: str | None = None

    while _running:
        try:
            data = _ha_request(token, "GET")
            entry_id = str(data["entry_id"])
            values = data["channels"]
            if not isinstance(values, list) or len(values) < 4:
                raise ValueError("Home Assistant returned invalid channel data")
            channels = [max(0, min(100, int(round(float(value))))) for value in values[:4]]
            shared.update_desired(entry_id, channels)
            if last_fetch_error is not None:
                log("INFO", "Home Assistant channel feed recovered.")
                last_fetch_error = None
        except (KeyError, TypeError, ValueError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
            text = str(err)
            if text != last_fetch_error:
                log("WARNING", f"Could not read desired channels from Home Assistant: {err}")
                last_fetch_error = text

        now = time.monotonic()
        if now >= next_status_post:
            snapshot = shared.snapshot()
            if snapshot["entry_id"]:
                try:
                    _ha_request(token, "POST", snapshot)
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as err:
                    log("WARNING", f"Could not publish bridge status to Home Assistant: {err}")
            next_status_post = now + STATUS_POST_SECONDS

        for _ in range(max(1, poll_interval * 10)):
            if not _running:
                break
            time.sleep(0.1)


def run_bridge(options: dict) -> None:
    shared = SharedBridgeState()
    worker = threading.Thread(
        target=home_assistant_worker,
        args=(shared, options["ha_poll_interval"]),
        daemon=True,
        name="reef-control-ha-api",
    )
    worker.start()

    device = None
    in_ep = None
    out_ep = None
    detached = False
    session_ready = False
    next_usb_attempt = 0.0
    last_logged_values: list[int] | None = None

    log("INFO", "Bridge mode enabled. Home Assistant controls SEA WATER channels 1-4; TC420 channel 5 remains fixed at 0%.")

    try:
        while _running:
            desired, last_ha_ok = shared.get_desired()
            ha_fresh = last_ha_ok > 0 and time.monotonic() - last_ha_ok <= HA_STALE_SECONDS

            if not ha_fresh:
                if session_ready:
                    log("WARNING", "Home Assistant channel data became stale. Stopping TC420 live keepalive.")
                    shared.set_usb_status(False, "home_assistant_data_stale")
                    close_device(device, detached)
                    device = in_ep = out_ep = None
                    detached = False
                    session_ready = False
                time.sleep(0.2)
                continue

            if not session_ready:
                now = time.monotonic()
                if now < next_usb_attempt:
                    time.sleep(0.1)
                    continue
                try:
                    device = find_controller()
                    if device is None:
                        raise RuntimeError("TC420 / SIMU-LUX not found")
                    log("INFO", f"TC420 detected for bridge mode: VID:PID={device.idVendor:04x}:{device.idProduct:04x}, bus={getattr(device, 'bus', None)}, address={getattr(device, 'address', None)}")
                    in_ep, out_ep, detached = open_device(device)
                    send_and_expect_ok(in_ep, out_ep, build_play_init_packet(), "Play init")
                    session_ready = True
                    shared.set_usb_status(True, "live")
                    log("INFO", "TC420 bridge live session established.")
                except Exception as err:
                    shared.set_usb_status(False, "usb_error", str(err))
                    log("ERROR", f"Could not establish TC420 bridge session: {err}")
                    close_device(device, detached)
                    device = in_ep = out_ep = None
                    detached = False
                    session_ready = False
                    next_usb_attempt = time.monotonic() + USB_RECONNECT_SECONDS
                    time.sleep(0.2)
                    continue

            values = desired[:4] + [0]
            try:
                send_and_expect_ok(in_ep, out_ep, build_play_channels_packet(values), "Play channels")
                shared.set_usb_status(True, "live")
                if last_logged_values != values:
                    log("INFO", f"Applied light channels: CH1={values[0]}%, CH2={values[1]}%, CH3={values[2]}%, CH4={values[3]}%, CH5=0%.")
                    last_logged_values = list(values)
            except Exception as err:
                shared.set_usb_status(False, "usb_error", str(err))
                log("ERROR", f"TC420 live channel update failed: {err}. Reconnecting bridge session...")
                close_device(device, detached)
                device = in_ep = out_ep = None
                detached = False
                session_ready = False
                next_usb_attempt = time.monotonic() + USB_RECONNECT_SECONDS
                time.sleep(0.2)
                continue

            slept = 0.0
            while _running and slept < LIVE_KEEPALIVE_SECONDS:
                time.sleep(0.05)
                slept += 0.05
    finally:
        shared.set_usb_status(False, "stopped")
        close_device(device, detached)
        log("INFO", "TC420 bridge mode stopped.")


def run_live_test(device, channel: int, level: int, seconds: int) -> bool:
    detached = False
    channel = max(1, min(4, int(channel)))
    level = max(0, min(20, int(level)))
    seconds = max(1, min(5, int(seconds)))
    values = [0, 0, 0, 0, 0]
    values[channel - 1] = level
    try:
        in_ep, out_ep, detached = open_device(device)
        log("WARNING", f"Starting temporary TC420 live test: CH{channel}={level}%, CH1-CH5={values}, duration={seconds}s.")
        send_and_expect_ok(in_ep, out_ep, build_play_init_packet("RCTEST"), "Play init")
        started = time.monotonic()
        sends = 0
        while _running and time.monotonic() - started < seconds:
            send_and_expect_ok(in_ep, out_ep, build_play_channels_packet(values), "Play channels")
            sends += 1
            time.sleep(LIVE_KEEPALIVE_SECONDS)
        log("INFO", f"Live test finished after {sends} channel updates.")
        log("INFO", "Fast-play keepalive stopped. Stored TC420 programs were not modified.")
        return True
    except Exception as err:
        log("ERROR", f"TC420 live test aborted safely: {err}")
        return False
    finally:
        close_device(device, detached)


def run_diagnostic_mode(options: dict) -> None:
    state = read_state()
    device = find_controller()
    if device is None:
        log("ERROR", "TC420 not found.")
        return
    log("INFO", f"TC420 detected: VID:PID={device.idVendor:04x}:{device.idProduct:04x}, bus={getattr(device, 'bus', None)}, address={getattr(device, 'address', None)}")
    if options["sync_time_on_connect"]:
        synchronize_clock(device)
        time.sleep(0.5)
    token = options["live_test_token"]
    last = int(state.get("last_live_test_token", 0) or 0)
    if token <= 0:
        log("INFO", "Bridge mode is disabled and no live test is armed.")
    elif token == last:
        log("INFO", f"Live test token {token} was already used. Skipping.")
    else:
        state["last_live_test_token"] = token
        state["last_live_test_result"] = "started"
        write_state(state)
        success = run_live_test(device, options["live_test_channel"], options["live_test_level"], options["live_test_seconds"])
        state["last_live_test_result"] = "success" if success else "failed"
        write_state(state)
    while _running:
        time.sleep(options["poll_interval"])


def main() -> None:
    options = read_options()
    log("INFO", f"Reef Control TC420 USB v{APP_VERSION}")
    log("INFO", f"USB robustness: settle={USB_SETTLE_SECONDS}s, retries={USB_RETRIES}, retry-delay={USB_RETRY_DELAY_SECONDS}s")
    log("INFO", "SEA WATER profile: channels 1-4 exposed, channel 5 fixed at 0%.")
    if options["bridge_enabled"]:
        run_bridge(options)
    else:
        run_diagnostic_mode(options)
    log("INFO", "Reef Control TC420 USB service stopped.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    main()
