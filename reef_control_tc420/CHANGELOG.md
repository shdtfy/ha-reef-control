# Changelog

## 0.3.0
- Added permanent Reef Control bridge mode.
- Added internal Home Assistant API communication using the Supervisor token.
- Added continuous TC420 fast-play keepalive.
- Added automatic USB session recovery.
- Added stale Home Assistant data protection.
- SEA WATER profile exposes channels 1-4 only.
- TC420 channel 5 is permanently held at 0% in bridge mode.
- Kept the previous one-shot diagnostic mode when bridge mode is disabled.
- Stored TC420 programs remain untouched.

## 0.2.2
- Fixed PyUSB Interface compatibility.
- Added endpoint diagnostics.
- Kept retry and timeout handling.

## 0.2.1
- Added USB settle delay and retry handling.

## 0.2.0
- Added guarded TC420 fast-play output test.
