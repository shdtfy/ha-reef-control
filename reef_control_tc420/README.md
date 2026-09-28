# Reef Control TC420 USB

Experimental Home Assistant app for direct USB communication with TC420 / LEDaquaristik SIMU-LUX controllers.

The first version is intentionally conservative:

- detects USB device `0888:4000`
- monitors connect/disconnect state in the app log
- can optionally synchronize the controller clock
- does **not** change channel brightness
- does **not** modify stored lighting programs

Once communication has been verified on the target controller, this service can become the USB hardware bridge for the Reef Control Home Assistant integration.
