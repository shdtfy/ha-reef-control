# Changelog

## 0.2.2
- Fixed PyUSB `Interface` compatibility issue from v0.2.1.
- Removed `len(interface)` usage.
- Access TC420 IN/OUT endpoints directly by fixed endpoint indices.
- Added endpoint-address diagnostics.
- Kept retry and timeout handling from v0.2.1.

## 0.2.1
- Added USB settle delay before first transfer.
- Added up to three retries for transient TC420 USB timeouts and USB errors.
- Clock-sync failures no longer terminate the app.
- Live-test failures no longer terminate the app.

## 0.2.0
- Added guarded TC420 fast-play output test.
- Added one-shot live-test token.
- Selectable channel CH1-CH5.
- Safety caps: maximum 20% brightness and 5 seconds.
