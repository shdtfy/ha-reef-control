# Reef Control TC420 USB

This experimental app is the first hardware bridge for Reef Control.

## Supported test hardware

The current diagnostic build expects a TC420 / SIMU-LUX controller with:

- USB vendor ID: `0888`
- USB product ID: `4000`

## First test: detection only

Keep the default option:

```yaml
sync_time_on_connect: false
poll_interval: 5
```

Start the app and open its log.

Expected output includes:

```text
TC420 detected: VID:PID=0888:4000
```

This test only searches for the controller. It does not send lighting commands.

## Second test: clock synchronization

After successful detection, enable:

```yaml
sync_time_on_connect: true
```

Restart the app.

The service then sends only the TC420 clock-sync command. It does not change channel brightness or stored programs.

Expected output:

```text
TC420 clock synchronization successful
```

## Safety

Version 0.1.0 deliberately contains no commands for CH1-CH5 and no program-writing code.

The next stage, after the clock-sync test succeeds, will add a temporary and explicitly controlled live-channel test before Reef Control gets full lighting support.
