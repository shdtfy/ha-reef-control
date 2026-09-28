# Reef Control TC420 USB v0.2.0

Recommended first live test:

```yaml
sync_time_on_connect: true
poll_interval: 5
live_test_token: 1
live_test_channel: 1
live_test_level: 10
live_test_seconds: 3
```

This requests CH1 at 10%, CH2-CH5 at 0% for 3 seconds.

Safety:
- max 20% brightness
- max 5 seconds
- one run per token
- stored TC420 programs are not modified

To run another test later, increase `live_test_token` to 2, 3, and so on.
