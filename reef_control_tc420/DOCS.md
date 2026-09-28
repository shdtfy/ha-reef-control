# Reef Control TC420 USB v0.2.1

This release improves USB robustness after intermittent TC420 response timeouts were observed.

## Changes
- 0.5 second settle delay after opening the TC420 interface
- up to 3 attempts per command
- 0.8 second delay between retries
- clock-sync failures no longer stop the app
- live-test failures no longer stop the app
- stored TC420 lighting programs are still never modified

## Recommended next test
Because token `1` was already consumed by the previous test attempt, use:

```yaml
sync_time_on_connect: false
poll_interval: 5
live_test_token: 2
live_test_channel: 1
live_test_level: 10
live_test_seconds: 3
```

If the controller times out once, the app should now log a retry instead of terminating.
