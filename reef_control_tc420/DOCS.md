# Reef Control TC420 USB v0.3.1

Version 0.3.0 turns the diagnostic USB app into a permanent Reef Control lighting bridge.

## SEA WATER channel profile

The SEA WATER light uses four TC420 channels. Reef Control therefore exposes only channels 1-4. TC420 channel 5 is always transmitted as **0%** and is not exposed as a Home Assistant control.

## Bridge mode

The app reads the desired channel values directly from the Reef Control custom integration through Home Assistant's internal API. No LAN port, MQTT broker, IP address, or additional authentication is required.

Recommended configuration after installing the matching Reef Control integration update:

```yaml
bridge_enabled: true
ha_poll_interval: 1
sync_time_on_connect: false
poll_interval: 5
live_test_token: 0
live_test_channel: 1
live_test_level: 10
live_test_seconds: 3
```

## Safety behavior

- Stored TC420 programs are never modified.
- Channel 5 stays at 0%.
- If Home Assistant channel data is unavailable for more than 10 seconds, the app stops sending fast-play keepalive packets.
- If USB communication fails, the bridge closes the session and retries.
- The three-attempt USB retry logic remains enabled.

## Home Assistant entities

The matching Reef Control integration update creates four `number` entities from 0 to 100 percent. These values are Reef Control **setpoints**, not physical readback values from the TC420.

## Play-init ACK fallback

Some TC420 / SIMU-LUX controllers accept the fast-play initialization command but do not return its ACK before the USB timeout. Version 0.3.1 keeps the existing retry logic, then clears delayed replies and probes fast-play with all five channels at 0%. If the probe is acknowledged, the bridge keeps the same USB session open and continues normally.
