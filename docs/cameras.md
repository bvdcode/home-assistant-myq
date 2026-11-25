# MyQ cameras

An attached camera appears on its opener's device page. A standalone camera
gets its own device with its MyQ name. You can also add an account that has
only cameras. Check the camera entity's `camera_serial_prefix` attribute to
identify its generation.

## Snapshots and live video

For garage cameras, Home Assistant requests snapshots from the Tend cloud on
demand. All viewers share the same image for 30 seconds.

TC cameras also support experimental live H.264 video through Home Assistant's
`stream` integration or its built-in go2rtc. Other generations offer snapshots
only. For a powered garage camera, see [using the stream in Frigate](frigate.md).

Viewers share one camera session. On garage cameras it closes 60 seconds after
the last viewer disconnects. Opening the camera in the myQ app at the same time
can interrupt playback. Live video has no audio. Cloud recordings cannot be
retrieved through the integration.

If playback fails, look for `TC camera live video unavailable` in the Home
Assistant logs. Standalone camera playback and recovery after a network
interruption still require device validation.

## Video Keypad previews and battery

The Video Keypad saves a frame locally during live viewing. Its dashboard
preview uses that frame even after an integration reload or a Home Assistant
restart. Open live view once to get the first preview. The **Snapshot time**
sensor and the `preview_updated` attribute show when it was captured.

Leave **Preload camera stream** off on a battery keypad. Live viewing draws
power and uses cloud signaling. The keypad session closes after 20 seconds
without a consumer, but Home Assistant's stream worker can stay connected
after you close the dashboard.

## Restrict camera video to the LAN

Under **Settings → Devices & services → MyQ → Configure**, enable **Require
LAN-only camera video**. Home Assistant must be able to reach the private IPv4
address the camera reports during authenticated signaling. The integration
accepts video only from the selected address and UDP port. If that path is
unreachable, playback fails.

The option is off by default. Changing it reloads the integration and closes
active camera sessions. MyQ still handles authorization, connection setup and
cloud snapshots. The camera can still upload video independently.
