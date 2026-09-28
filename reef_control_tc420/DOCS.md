# Reef Control TC420 USB v0.2.2

## Fix

v0.2.1 exposed a PyUSB compatibility issue:

```text
object of type 'Interface' has no len()
```

The TC420 interface is now accessed directly through endpoint indexes `0` and `1`,
matching the known TC420 implementation. No `len(interface)` call is used anymore.

The retry handling from v0.2.1 remains active:
- 0.5 s settle delay
- up to 3 attempts
- 0.8 s delay between attempts
- USB timeouts do not terminate the app

## Recommended next test

Tokens `1` and `2` have already been consumed. Use:

```yaml
sync_time_on_connect: false
poll_interval: 5
live_test_token: 3
live_test_channel: 1
live_test_level: 10
live_test_seconds: 3
```
