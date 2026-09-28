"""Safe TC420 / SIMU-LUX USB diagnostic service for Reef Control.

v0.1.1 keeps the first diagnostic stage intentionally conservative:
it detects the controller and can synchronize only its internal clock.
Channel levels and stored lighting programs are never modified.
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

APP_VERSION = "0.1.1"

VENDOR_ID = 0x0888
PRODUCT_ID = 0x4000
INTERFACE = 0
PACKET_SIZE = 64
USB_TIMEOUT_MS = 5000
TIME_SYNC_COMMAND = 0x11
OPTIONS_PATH = Path("/data/options.json")

_running = True


def log(level: str, message: str) -> None:
    print(f"[{level}] {message}", flush=True)


def _handle_stop(signum, frame) -> None:  # noqa: ARG001
    global _running
    _running = False


def read_options() -> tuple[bool, int]:
    try:
        data = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}

    sync_time = bool(data.get("sync_time_on_connect", False))

    try:
        poll_interval = int(data.get("poll_interval", 5))
    except (TypeError, ValueError):
        poll_interval = 5

    return sync_time, max(2, min(60, poll_interval))


def find_controller():
    return usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)


def build_packet(command: int, data: bytes = b"") -> bytes:
    """Create one 64-byte TC420 protocol packet."""
    if len(data) > 56:
        raise ValueError("TC420 payload is too large")

    packet = bytearray(PACKET_SIZE)
    packet[0:2] = b"\x55\xaa"
    packet[2] = command & 0xFF
    struct.pack_into("!H", packet, 3, len(data))
    packet[5 : 5 + len(data)] = data

    # TC420 checksum is the additive checksum over bytes 0..60.
    packet[61] = sum(packet[:61]) & 0xFF
    packet[62] = 0x0D
    packet[63] = 0x0A
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
    return build_packet(TIME_SYNC_COMMAND, payload)


def _endpoint_description(endpoint) -> str:
    address = int(endpoint.bEndpointAddress)
    direction = (
        "IN"
        if usb.util.endpoint_direction(address) == usb.util.ENDPOINT_IN
        else "OUT"
    )
    return f"0x{address:02x} ({direction})"


def open_tc420_interface(device):
    """Open the TC420 exactly using interface 0 and its two fixed endpoints.

    The known TC420 implementation uses interface (0, 0), endpoint index 0
    for input and endpoint index 1 for output. We follow that layout here
    instead of claiming and rediscovering endpoints ourselves.
    """
    detached_kernel_driver = False

    try:
        if device.is_kernel_driver_active(INTERFACE):
            device.detach_kernel_driver(INTERFACE)
            detached_kernel_driver = True
            log("INFO", "Detached kernel HID driver from interface 0.")
    except (NotImplementedError, usb.core.USBError) as err:
        log("WARNING", f"Could not query/detach kernel driver: {err}")

    configuration = device[0]
    interface = configuration[(INTERFACE, 0)]

    if len(interface) < 2:
        raise RuntimeError(
            f"TC420 interface exposes only {len(interface)} endpoint(s), expected 2"
        )

    in_ep = interface[0]
    out_ep = interface[1]

    in_direction = usb.util.endpoint_direction(in_ep.bEndpointAddress)
    out_direction = usb.util.endpoint_direction(out_ep.bEndpointAddress)

    log(
        "INFO",
        "TC420 endpoints: "
        f"intf[0]={_endpoint_description(in_ep)}, "
        f"intf[1]={_endpoint_description(out_ep)}",
    )

    if in_direction != usb.util.ENDPOINT_IN:
        raise RuntimeError(
            "Unexpected TC420 endpoint layout: interface endpoint 0 is not IN"
        )
    if out_direction != usb.util.ENDPOINT_OUT:
        raise RuntimeError(
            "Unexpected TC420 endpoint layout: interface endpoint 1 is not OUT"
        )

    return in_ep, out_ep, detached_kernel_driver


def close_tc420_interface(device, detached_kernel_driver: bool) -> None:
    """Release PyUSB resources and restore the HID kernel driver if possible."""
    usb.util.dispose_resources(device)

    if detached_kernel_driver:
        try:
            device.attach_kernel_driver(INTERFACE)
            log("INFO", "Reattached kernel HID driver to interface 0.")
        except (NotImplementedError, usb.core.USBError) as err:
            log("WARNING", f"Could not reattach kernel HID driver: {err}")


def synchronize_clock(device) -> None:
    """Synchronize the TC420 clock without touching channels or programs."""
    detached_kernel_driver = False

    try:
        in_ep, out_ep, detached_kernel_driver = open_tc420_interface(device)

        now = datetime.now()
        packet = build_time_sync_packet(now)

        log(
            "INFO",
            "Sending TC420 clock-sync command "
            f"for {now.strftime('%Y-%m-%d %H:%M:%S')}...",
        )

        written = out_ep.write(packet, timeout=USB_TIMEOUT_MS)
        log("INFO", f"Clock-sync packet written: {written}/{PACKET_SIZE} bytes.")

        response = bytes(in_ep.read(PACKET_SIZE, timeout=USB_TIMEOUT_MS))
        log("INFO", f"TC420 response received: {len(response)} bytes.")

        if len(response) < 6:
            raise RuntimeError(
                f"TC420 returned a short response ({len(response)} bytes)"
            )

        data_len = int.from_bytes(response[3:5], byteorder="big")
        status = response[5] if data_len >= 1 else None

        if data_len != 1 or status != 0x00:
            raise RuntimeError(
                "TC420 did not acknowledge clock synchronization "
                f"(data_len={data_len}, status={status!r})"
            )

        log(
            "INFO",
            "TC420 clock synchronization successful: "
            f"{now.strftime('%Y-%m-%d %H:%M:%S')}",
        )

    finally:
        close_tc420_interface(device, detached_kernel_driver)


def describe_device(device) -> str:
    bus = getattr(device, "bus", None)
    address = getattr(device, "address", None)

    location = ""
    if bus is not None and address is not None:
        location = f", bus={bus}, address={address}"

    return f"VID:PID={device.idVendor:04x}:{device.idProduct:04x}{location}"


def main() -> None:
    sync_time_on_connect, poll_interval = read_options()

    log("INFO", f"Reef Control TC420 USB v{APP_VERSION}")
    log(
        "INFO",
        f"Watching for TC420 / SIMU-LUX {VENDOR_ID:04x}:{PRODUCT_ID:04x}",
    )
    log("INFO", f"Poll interval: {poll_interval} s")
    log(
        "INFO",
        "Clock sync on connect: "
        + ("enabled" if sync_time_on_connect else "disabled"),
    )
    log(
        "INFO",
        "Safety mode active: channel levels and stored programs are never changed.",
    )

    connected = False
    sync_attempted = False

    while _running:
        try:
            device = find_controller()
        except usb.core.NoBackendError:
            log("ERROR", "No libusb backend is available.")
            time.sleep(poll_interval)
            continue
        except usb.core.USBError as err:
            log("ERROR", f"USB discovery failed: {err}")
            time.sleep(poll_interval)
            continue

        if device is not None and not connected:
            connected = True
            sync_attempted = False
            log("INFO", "TC420 detected: " + describe_device(device))

        elif device is None and connected:
            connected = False
            sync_attempted = False
            log("WARNING", "TC420 disconnected.")

        if device is not None and sync_time_on_connect and not sync_attempted:
            sync_attempted = True
            try:
                synchronize_clock(device)
            except usb.core.USBError as err:
                log(
                    "ERROR",
                    "TC420 clock synchronization failed with USB error: "
                    f"{err}",
                )
            except Exception as err:
                log("ERROR", f"TC420 clock synchronization failed: {err}")

        time.sleep(poll_interval)

    log("INFO", "Reef Control TC420 USB service stopped.")


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    main()
