# Changelog

## 0.1.1

- Align TC420 USB communication with the known controller endpoint layout.
- Use interface `(0, 0)` directly.
- Use endpoint index `0` as IN and endpoint index `1` as OUT.
- Remove explicit PyUSB interface claiming from the clock-sync test.
- Add endpoint, write-length and response diagnostics.
- Keep the safety restriction: no channel-level or stored-program commands.

## 0.1.0

- Initial TC420 / SIMU-LUX USB diagnostic app.
- Detects controllers with USB ID `0888:4000`.
- Monitors controller connect/disconnect state in the log.
- Optional clock synchronization.
- No channel-level or stored-program modification.
