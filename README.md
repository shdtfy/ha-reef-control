# Reef Control TC420 USB

Home Assistant app that provides the USB hardware bridge between Reef Control and TC420 / LEDaquaristik SIMU-LUX lighting controllers (`0888:4000`).

Current bridge behavior:

- controls SEA WATER channels 1-4 from Reef Control
- keeps TC420 channel 5 at 0%
- uses the controller fast-play/live mode
- keeps the live channel values refreshed in the background
- retries USB communication and reconnects after real communication failures
- tolerates the known missing/delayed Play-init ACK quirk by probing fast-play safely at 0%
- never modifies stored TC420 lighting programs

The Home Assistant integration exposes the four light-channel setpoints and the TC420 bridge connection status. The displayed percentages are Reef Control setpoints, not physical output readback from the controller.
