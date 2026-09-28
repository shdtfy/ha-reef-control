"""TC420 / SIMU-LUX USB bridge for Reef Control v0.2.2.

Fixes PyUSB Interface handling from v0.2.1.
Stored TC420 programs are never modified.
"""

from __future__ import annotations

import json
import signal
import struct
import time
from datetime import datetime
from pathlib import Path

import usb.core
import usb.util

APP_VERSION = "0.2.2"

VENDOR_ID = 0x0888
PRODUCT_ID = 0x4000
INTERFACE = 0
PACKET_SIZE = 64

USB_TIMEOUT_MS = 5000
USB_RETRIES = 3
USB_SETTLE_SECONDS = 0.5
USB_RETRY_DELAY_SECONDS = 0.8

CMD_TIME_SYNC = 0x11
CMD_PLAY_INIT = 0x15
CMD_PLAY_SET_CHANNELS = 0x16

OPTIONS_PATH = Path("/data/options.json")
STATE_PATH = Path("/data/tc420_state.json")

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
        "sync_time_on_connect": bool(data.get("sync_time_on_connect", False)),
        "poll_interval": max(2, min(60, _as_int(data, "poll_interval", 5))),
        "live_test_token": max(0, _as_int(data, "live_test_token", 0)),
        "live_test_channel": max(1, min(5, _as_int(data, "live_test_channel", 1))),
        "live_test_level": max(0, min(20, _as_int(data, "live_test_level", 10))),
        "live_test_seconds": max(1, min(5, _as_int(data, "live_test_seconds", 3))),
    }


def read_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def find_controller():
    return usb.core.find(
        idVendor=VENDOR_ID,
        idProduct=PRODUCT_ID,
    )


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
    payload = struct.pack(
        "!HBBBBB",
        now.year,
        now.month,
        now.day,
        now.hour,
        now.minute,
        now.second,
    )
    return build_packet(CMD_TIME_SYNC, payload)


def build_play_init_packet(name: str = "RCTEST") -> bytes:
    name_bytes = name.encode("ascii", errors="replace")[:8] or b"RCTEST"
    return build_packet(
        CMD_PLAY_INIT,
        name_bytes + struct.pack("!H", 0x007F),
    )


def build_play_channels_packet(values: list[int]) -> bytes:
    if len(values) != 5:
        raise ValueError("Exactly five TC420 channel values are required")

    vals = [max(0, min(100, int(v))) for v in values]
    return build_packet(
        CMD_PLAY_SET_CHANNELS,
        bytes([0xF5, *vals, 0x00]),
    )


def open_device(device):
    detached = False

    try:
        if device.is_kernel_driver_active(INTERFACE):
            device.detach_kernel_driver(INTERFACE)
            detached = True
            log("INFO", "Detached kernel HID driver from interface 0.")
    except (NotImplementedError, usb.core.USBError) as err:
        log(
            "WARNING",
            f"Could not query or detach kernel HID driver: {err}",
        )

    interface = device[0][(INTERFACE, 0)]

    # PyUSB Interface objects are indexable, but not all versions implement
    # __len__. The known TC420 library uses these two fixed endpoint indices.
    try:
        in_ep = interface[0]
        out_ep = interface[1]
    except (IndexError, TypeError) as err:
        raise RuntimeError(
            "TC420 interface does not expose the expected two endpoints"
        ) from err

    if (
        usb.util.endpoint_direction(in_ep.bEndpointAddress)
        != usb.util.ENDPOINT_IN
    ):
        raise RuntimeError(
            "Unexpected TC420 endpoint layout: endpoint 0 is not IN"
        )

    if (
        usb.util.endpoint_direction(out_ep.bEndpointAddress)
        != usb.util.ENDPOINT_OUT
    ):
        raise RuntimeError(
            "Unexpected TC420 endpoint layout: endpoint 1 is not OUT"
        )

    log(
        "INFO",
        "TC420 endpoints ready: "
        f"IN=0x{int(in_ep.bEndpointAddress):02x}, "
        f"OUT=0x{int(out_ep.bEndpointAddress):02x}",
    )

    time.sleep(USB_SETTLE_SECONDS)
    return in_ep, out_ep, detached


def close_device(device, detached: bool) -> None:
    usb.util.dispose_resources(device)

    if detached:
        try:
            device.attach_kernel_driver(INTERFACE)
            log("INFO", "Reattached kernel HID driver to interface 0.")
        except (NotImplementedError, usb.core.USBError) as err:
            log(
                "WARNING",
                f"Could not reattach kernel HID driver: {err}",
            )


def parse_ack(response: bytes, label: str) -> None:
    if len(response) < 6:
        raise RuntimeError(
            f"{label}: short TC420 response ({len(response)} bytes)"
        )

    data_len = int.from_bytes(response[3:5], byteorder="big")
    status = response[5] if data_len >= 1 else None

    if data_len != 1 or status != 0x00:
        raise RuntimeError(
            f"{label}: controller did not acknowledge "
            f"(data_len={data_len}, status={status!r})"
        )


def send_and_expect_ok(in_ep, out_ep, packet: bytes, label: str) -> None:
    last_error: Exception | None = None

    for attempt in range(1, USB_RETRIES + 1):
        try:
            written = out_ep.write(
                packet,
                timeout=USB_TIMEOUT_MS,
            )

            if written != PACKET_SIZE:
                raise RuntimeError(
                    f"{label}: wrote {written}/{PACKET_SIZE} bytes"
                )

            response = bytes(
                in_ep.read(
                    PACKET_SIZE,
                    timeout=USB_TIMEOUT_MS,
                )
            )

            parse_ack(response, label)

            if attempt > 1:
                log(
                    "INFO",
                    f"{label}: succeeded on retry "
                    f"{attempt}/{USB_RETRIES}.",
                )

            return

        except (
            usb.core.USBTimeoutError,
            usb.core.USBError,
            RuntimeError,
        ) as err:
            last_error = err

            if attempt < USB_RETRIES:
                log(
                    "WARNING",
                    f"{label}: attempt {attempt}/{USB_RETRIES} "
                    f"failed: {err}; retrying...",
                )
                time.sleep(USB_RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"{label}: failed after {USB_RETRIES} attempts: {last_error}"
    )


def synchronize_clock(device) -> bool:
    detached = False

    try:
        in_ep, out_ep, detached = open_device(device)
        now = datetime.now()

        send_and_expect_ok(
            in_ep,
            out_ep,
            build_time_sync_packet(now),
            "Clock sync",
        )

        log(
            "INFO",
            "TC420 clock synchronization successful: "
            f"{now:%Y-%m-%d %H:%M:%S}",
        )
        return True

    except Exception as err:
        log(
            "WARNING",
            f"TC420 clock synchronization skipped after retries: {err}",
        )
        return False

    finally:
        close_device(device, detached)


def run_live_test(
    device,
    channel: int,
    level: int,
    seconds: int,
) -> bool:
    detached = False

    channel = max(1, min(5, int(channel)))
    level = max(0, min(20, int(level)))
    seconds = max(1, min(5, int(seconds)))

    values = [0, 0, 0, 0, 0]
    values[channel - 1] = level

    try:
        in_ep, out_ep, detached = open_device(device)

        log(
            "WARNING",
            "Starting temporary TC420 live test: "
            f"CH{channel}={level}%, "
            f"CH1-CH5={values}, "
            f"duration={seconds}s.",
        )

        send_and_expect_ok(
            in_ep,
            out_ep,
            build_play_init_packet(),
            "Play init",
        )

        started = time.monotonic()
        sends = 0

        while _running and time.monotonic() - started < seconds:
            send_and_expect_ok(
                in_ep,
                out_ep,
                build_play_channels_packet(values),
                "Play channels",
            )
            sends += 1
            time.sleep(0.4)

        log(
            "INFO",
            f"Live test finished after {sends} channel updates.",
        )
        log(
            "INFO",
            "Fast-play keepalive stopped. "
            "Stored TC420 programs were not modified.",
        )
        return True

    except Exception as err:
        log(
            "ERROR",
            f"TC420 live test aborted safely: {err}",
        )
        return False

    finally:
        close_device(device, detached)


def describe_device(device) -> str:
    return (
        f"VID:PID={device.idVendor:04x}:{device.idProduct:04x}, "
        f"bus={getattr(device, 'bus', None)}, "
        f"address={getattr(device, 'address', None)}"
    )


def main() -> None:
    options = read_options()
    state = read_state()

    log("INFO", f"Reef Control TC420 USB v{APP_VERSION}")
    log(
        "INFO",
        f"USB robustness: settle={USB_SETTLE_SECONDS}s, "
        f"retries={USB_RETRIES}, "
        f"retry-delay={USB_RETRY_DELAY_SECONDS}s",
    )
    log(
        "INFO",
        "Safety caps: max 20%, max 5 seconds. "
        "Stored programs are untouched.",
    )

    device = find_controller()

    if device is None:
        log("ERROR", "TC420 not found.")
        return

    log("INFO", "TC420 detected: " + describe_device(device))

    if options["sync_time_on_connect"]:
        synchronize_clock(device)
        time.sleep(0.5)

    token = options["live_test_token"]
    last = int(state.get("last_live_test_token", 0) or 0)

    if token <= 0:
        log(
            "INFO",
            "Live test not armed. "
            "Set live_test_token to a new positive number.",
        )

    elif token == last:
        log(
            "INFO",
            f"Live test token {token} was already used. Skipping.",
        )

    else:
        state["last_live_test_token"] = token
        state["last_live_test_result"] = "started"
        write_state(state)

        success = run_live_test(
            device,
            options["live_test_channel"],
            options["live_test_level"],
            options["live_test_seconds"],
        )

        state["last_live_test_result"] = (
            "success" if success else "failed"
        )
        write_state(state)

    while _running:
        time.sleep(options["poll_interval"])

    log("INFO", "Reef Control TC420 USB service stopped.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    main()
