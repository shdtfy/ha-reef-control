"""TC420 / SIMU-LUX USB bridge for Reef Control v0.2.0."""
from __future__ import annotations
import json, signal, struct, time
from datetime import datetime
from pathlib import Path
import usb.core, usb.util

APP_VERSION = "0.2.0"
VENDOR_ID = 0x0888
PRODUCT_ID = 0x4000
INTERFACE = 0
PACKET_SIZE = 64
USB_TIMEOUT_MS = 5000
CMD_TIME_SYNC = 0x11
CMD_PLAY_INIT = 0x15
CMD_PLAY_SET_CHANNELS = 0x16
OPTIONS_PATH = Path("/data/options.json")
STATE_PATH = Path("/data/tc420_state.json")
_running = True

def log(level, msg):
    print(f"[{level}] {msg}", flush=True)

def _stop(signum, frame):
    global _running
    _running = False

def _int(data, key, default):
    try:
        return int(data.get(key, default))
    except (TypeError, ValueError):
        return default

def read_options():
    try:
        data = json.loads(OPTIONS_PATH.read_text())
    except Exception:
        data = {}
    return {
        "sync_time_on_connect": bool(data.get("sync_time_on_connect", False)),
        "poll_interval": max(2, min(60, _int(data, "poll_interval", 5))),
        "live_test_token": max(0, _int(data, "live_test_token", 0)),
        "live_test_channel": max(1, min(5, _int(data, "live_test_channel", 1))),
        "live_test_level": max(0, min(20, _int(data, "live_test_level", 10))),
        "live_test_seconds": max(1, min(5, _int(data, "live_test_seconds", 3))),
    }

def read_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}

def write_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True))

def build_packet(command, data=b""):
    packet = bytearray(PACKET_SIZE)
    packet[0:2] = b"\x55\xaa"
    packet[2] = command
    struct.pack_into("!H", packet, 3, len(data))
    packet[5:5+len(data)] = data
    packet[61] = sum(packet[:61]) & 0xff
    packet[62:64] = b"\x0d\x0a"
    return bytes(packet)

def time_packet(now=None):
    now = now or datetime.now()
    return build_packet(CMD_TIME_SYNC, struct.pack("!HBBBBB",
        now.year, now.month, now.day, now.hour, now.minute, now.second))

def play_init_packet(name="RCTEST"):
    payload = name.encode("ascii", errors="replace")[:8] + struct.pack("!H", 0x007f)
    return build_packet(CMD_PLAY_INIT, payload)

def play_channels_packet(values):
    vals = [max(0, min(100, int(v))) for v in values]
    return build_packet(CMD_PLAY_SET_CHANNELS, bytes([0xf5, *vals, 0x00]))

def open_dev(dev):
    detached = False
    try:
        if dev.is_kernel_driver_active(INTERFACE):
            dev.detach_kernel_driver(INTERFACE)
            detached = True
    except Exception:
        pass
    intf = dev[0][(0, 0)]
    return intf[0], intf[1], detached

def close_dev(dev, detached):
    usb.util.dispose_resources(dev)
    if detached:
        try:
            dev.attach_kernel_driver(INTERFACE)
        except Exception:
            pass

def send_ok(inp, out, packet, label):
    written = out.write(packet, timeout=USB_TIMEOUT_MS)
    if written != 64:
        raise RuntimeError(f"{label}: wrote {written}/64 bytes")
    response = bytes(inp.read(64, timeout=USB_TIMEOUT_MS))
    if len(response) < 6:
        raise RuntimeError(f"{label}: short response")
    data_len = int.from_bytes(response[3:5], "big")
    status = response[5] if data_len >= 1 else None
    if data_len != 1 or status != 0:
        raise RuntimeError(f"{label}: no ACK (len={data_len}, status={status})")

def sync_clock(dev):
    detached = False
    try:
        inp, out, detached = open_dev(dev)
        now = datetime.now()
        send_ok(inp, out, time_packet(now), "Clock sync")
        log("INFO", f"TC420 clock synchronization successful: {now:%Y-%m-%d %H:%M:%S}")
    finally:
        close_dev(dev, detached)

def run_live_test(dev, channel, level, seconds):
    detached = False
    values = [0, 0, 0, 0, 0]
    values[channel-1] = level
    try:
        inp, out, detached = open_dev(dev)
        log("WARNING", f"Live test: CH{channel}={level}%, others=0%, {seconds}s")
        send_ok(inp, out, play_init_packet(), "Play init")
        started = time.monotonic()
        sends = 0
        while _running and time.monotonic() - started < seconds:
            send_ok(inp, out, play_channels_packet(values), "Play channels")
            sends += 1
            time.sleep(0.4)
        log("INFO", f"Live test finished after {sends} updates. Fast-play keepalive stopped.")
        log("INFO", "Stored TC420 programs were not modified.")
    finally:
        close_dev(dev, detached)

def main():
    opts = read_options()
    state = read_state()
    log("INFO", f"Reef Control TC420 USB v{APP_VERSION}")
    log("INFO", "Safety caps: max 20%, max 5 seconds. Stored programs are untouched.")

    dev = usb.core.find(idVendor=VENDOR_ID, idProduct=PRODUCT_ID)
    if dev is None:
        log("ERROR", "TC420 not found.")
        return

    log("INFO", f"TC420 detected: VID:PID={dev.idVendor:04x}:{dev.idProduct:04x}, bus={getattr(dev,'bus',None)}, address={getattr(dev,'address',None)}")

    if opts["sync_time_on_connect"]:
        sync_clock(dev)

    token = opts["live_test_token"]
    last = int(state.get("last_live_test_token", 0) or 0)

    if token <= 0:
        log("INFO", "Live test not armed. Set live_test_token to a new positive number.")
    elif token == last:
        log("INFO", f"Live test token {token} already used. Skipping.")
    else:
        state["last_live_test_token"] = token
        write_state(state)
        run_live_test(dev, opts["live_test_channel"], opts["live_test_level"], opts["live_test_seconds"])

    while _running:
        time.sleep(opts["poll_interval"])

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    main()
