# Changelog

## 0.2.1
- Added USB settle delay before first transfer.
- Added up to three retries for transient TC420 USB timeouts and USB errors.
- Added delay between retries.
- Clock-sync failures no longer terminate the app.
- Live-test failures no longer terminate the app.
- Store the last live-test result internally.
- Stored TC420 programs remain untouched.

## 0.2.0
- Added guarded TC420 fast-play output test.
- Added one-shot live-test token.
- Selectable channel CH1-CH5.
- Safety caps: maximum 20% brightness and 5 seconds.

## 0.1.1
- Fixed TC420 USB endpoint handling.
- Clock synchronization confirmed working.
