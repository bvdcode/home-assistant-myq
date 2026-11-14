# MyQ for Home Assistant

[![CI](https://github.com/bvdcode/home-assistant-myq/actions/workflows/ci.yml/badge.svg)](https://github.com/bvdcode/home-assistant-myq/actions/workflows/ci.yml)
[![HACS](https://github.com/bvdcode/home-assistant-myq/actions/workflows/hacs.yml/badge.svg)](https://github.com/bvdcode/home-assistant-myq/actions/workflows/hacs.yml)
[![Hassfest](https://github.com/bvdcode/home-assistant-myq/actions/workflows/hassfest.yml/badge.svg)](https://github.com/bvdcode/home-assistant-myq/actions/workflows/hassfest.yml)
[![Support on Ko-fi](https://img.shields.io/badge/Support_on_Ko--fi-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/bvdcode)


MyQ connects Chamberlain and LiftMaster garage-door openers to Home Assistant
through the MyQ residential cloud service.

> If this integration makes your daily life a little easier, consider
> [supporting the project on Ko-fi](https://ko-fi.com/bvdcode)

The integration provides:

- configuration entirely through the Home Assistant user interface;
- email or SMS verification during sign-in;
- automatic OAuth token refresh while authorization remains valid;
- discovery of garage doors exposed by the MyQ account;
- current door state and cloud availability;
- open and close controls;
- a door-open binary sensor for Alarmo and other sensor-based automations;
- vacation mode, work-light, fault, cycle-count, and activation diagnostics
  when provided by MyQ;
- snapshots from attached and standalone cameras and experimental live video for TC cameras;
- a sidebar panel and dashboard card with realistic, customizable garage doors, controls, status,
  recent activity, and camera video;
- cloud polling every 2 minutes, temporarily more frequently after a command.

## Alarmo

Each garage door includes a **Door open** binary sensor with the `garage_door` device class. Add this sensor in Alarmo's **Sensors** tab. The existing cover provides the open and close controls.

The sensor is on whenever the door is known to be not closed, including while it is moving. Unknown states remain unknown, and offline or missing doors are unavailable. The sensor shares cloud polling with the cover. Changes made outside Home Assistant may take up to 2 minutes to appear. Account membership is refreshed every 15 minutes; device states are read on each poll.

After an accepted open or close command, the integration waits 1 second before checking the status. The intervals then increase to 2, 3, 4, and 5 seconds and remain at 5 seconds. Polling continues for at least 30 seconds, even if the requested state is reported earlier, and for up to 60 seconds while waiting for it. A new command restarts the sequence and polling window for that door. After an accepted command from a fully closed or open door, the cover immediately shows Opening or Closing. The cover keeps this provisional movement while MyQ still reports the original state, until a different state arrives or the 60-second tracking timeout is reached. After a different state is reported, the cover follows all subsequent MyQ states, including a reversal. All sensors continue to use confirmed MyQ data. Polling returns to the normal 2-minute interval when tracking finishes or the door becomes unavailable. Failed background updates retry after 4, 8, and then 15 minutes; a successful update restores the normal interval. Longer server-requested retry delays are respected. If polling is disabled in Home Assistant system options, commands keep the last confirmed state without provisional movement or automatic status requests; manual updates still work.

## Requirements

- Home Assistant 2026.7.4 or newer;
- a MyQ residential account with at least one connected garage-door opener.

The initial release has been tested with a United States MyQ account. Reports
from other regions are welcome.

## Installation

The integration can be installed through HACS as a custom repository.

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=bvdcode&repository=home-assistant-myq&category=integration)

1. Open **HACS**.
2. Select **Integrations**.
3. Open the menu and select **Custom repositories**.
4. Add `https://github.com/bvdcode/home-assistant-myq` as an **Integration**
   repository.
5. Install **MyQ** and restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up MyQ.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=myq)

1. Open **Settings → Devices & services**.
2. Select **Add integration**.
3. Search for **MyQ**.
4. Choose automatic or browser sign-in.
5. For automatic sign-in, enter the email address and password used by the
   MyQ app, then select email or SMS delivery and enter the six-digit
   verification code.

Browser sign-in is always available and is also offered automatically if MyQ
blocks the automatic flow. Enter the account email address, complete
authentication on the MyQ website, and paste the resulting
`com.myqops://android` callback address into Home Assistant.

If the callback address does not appear, press **F12**, open the browser
console, and find the message that starts with
`Failed to launch 'com.myqops://android?` and says that the scheme does not
have a registered handler. Copy the complete `com.myqops://android?...`
address from that message and paste it into Home Assistant.

Browser sign-in completes the interactive login step. It does not bypass
restrictions on token exchange or device API access.

The password is used only during sign-in and is not stored. Home Assistant
stores the issued OAuth tokens in the config entry and refreshes them
automatically. If MyQ rejects token refresh or account access, Home Assistant
requests reauthentication.

## Garage panel

The integration can add a **MyQ** page to the Home Assistant sidebar. The page
is off by default. To turn it on, open **Settings → Devices & services → MyQ →
Configure** and select **Show the garage panel in the sidebar**. It finds every
garage door and camera on the account automatically and updates as soon as
devices are added, renamed, or removed in Home Assistant.

Each door is drawn as a realistic garage door framed by its trim. The door moves
when it opens or closes, the garage interior shows through windows and open
doors, and the interior lights up when the opener's work light is on. Below each
door are **Open** and **Close** buttons, the time of the last change, and chips
for the work light, vacation mode, faults, and battery backup. **Details** lists
every entity of the door; select one to open its details and history. It also
lists the last five times the door opened or closed in the past week, with the
person or automation that caused each change when Home Assistant knows it, and
the MyQ source of the latest change, such as the MyQ app.

Open doors show how long they have been open. A door left open longer than the
panel's limit, 30 minutes unless changed in the panel settings, gets an amber
outline, and the summary at the top names it.

Door states can be up to 2 minutes old because MyQ is polled. The refresh
button next to a door's name asks MyQ for the current state right away; it then
rests for 15 seconds. In the Home Assistant phone apps, the phone vibrates when
a command is sent, when a second tap is needed, and when a command fails.

The list button in the toolbar switches to compact cards, with the door picture
beside the name and only the button that applies, so several doors fit on a
phone screen. Narrow screens use compact cards automatically when there are
three or more doors. Each browser remembers its own choice.

Doors with an attached camera have a camera button that swaps the drawing for
snapshots, with **Live** video for TC cameras. Standalone cameras such as the
myQ Video Keypad appear in their own section. Snapshots refresh every 30 seconds,
and only while a camera is on screen in a visible browser tab. All viewers share
the integration's 30-second snapshot cache, so several open panels do not
multiply MyQ requests. Live video starts only when requested. When a door with a
camera stops moving, a new snapshot appears over the door for 20 seconds, so you
can see where it stopped; select it to switch to the camera.

Administrators can select the palette button on a door to change its look:

- single or double width;
- raised panel, long panel, shaker, carriage house, farmhouse, flush, plank, or
  full-view glass style;
- painted, wood-look, or any custom color;
- plain, grid, arched, or side windows, depending on the style, with tinted,
  clear, or frosted glass;
- decorative handles and hinges for carriage styles;
- the color of the trim around the door.

The look is stored in Home Assistant and shared by everyone who opens the panel,
and it can be applied to every door at once. The gear button holds panel-wide
settings: the order of the doors, an option to require a second tap before a
door moves, and how long a door may stay open before it is highlighted. **Close
all** always asks for a second tap.

The same **Configure** page sets the panel's title, icon, and audience. With
several MyQ accounts, the panel shows the doors of every account that enables
it, and the first such account sets the sidebar title and icon.

## Dashboard card

Each garage door is also available as a dashboard card with the same picture,
controls, status, camera, and recent activity as the panel. The integration
loads the card itself, so no dashboard resource is needed, and the card works
without the sidebar panel. In a dashboard, select **Add card** and
search for **MyQ garage door**, or add it in YAML:

```yaml
type: custom:myq-door-card
entity: cover.main_garage
compact: false
```

Set `compact` to `true` for a short card with the door picture beside the
controls. Administrators can change the door's look from the card; the look is
shared with the panel. Cards use the panel's settings for the second tap and the
open-door highlight.

## Cameras

Cameras that are not attached to an opener, including the myQ Video Keypad,
get their own device using their MyQ name. Accounts containing only cameras
can also be added.

Openers with an attached camera get a camera entity on the same device.
Snapshots are fetched on demand from the Tend cloud using the existing MyQ
authorization. All viewers share one cached image per camera for 30 seconds;
when the door moves, the next request takes a new image.

TC cameras also offer experimental live H.264 video. Home Assistant must be able
to reach the camera over the local network. Playback uses the `stream`
integration or Home Assistant's built-in go2rtc. An external go2rtc server on
another host or in another container cannot access the loopback video source.
Other camera generations currently provide snapshots only.

Viewers share one camera session, which closes 60 seconds after the last viewer
disconnects. Opening the camera simultaneously in the myQ app may interrupt the
session. Audio and retrieval of cloud recordings are not implemented.

The `camera_serial_prefix` attribute identifies the camera generation. Connection
failures are logged with `TC camera live video unavailable`. Standalone camera playback
and recovery after a network interruption still require device validation.

## Safety

Opening or closing a garage door can cause injury or property damage. Keep the
door area clear and maintain the opener's photo eyes, obstruction detection,
and other safety equipment. Do not use remote control where unattended
operation is prohibited.

## Development

Use Python 3.14 or newer and install the test dependencies:

```bash
python -m pip install -r requirements_test.txt
ruff check .
ruff format --check .
mypy custom_components/myq tests
pytest
```

## Project status

This is a community-maintained project and is not affiliated with, endorsed by,
or associated with The Chamberlain Group LLC. MyQ, Chamberlain, and LiftMaster
are trademarks of their respective owners.

### Restrict camera video to the LAN

In **Settings → Devices & services → MyQ → Configure**, enable **Require LAN-only
camera video** to accept video only from the camera's RFC1918 IPv4 address reported
by authenticated signaling. The selected UDP peer's address and port are pinned;
public or different private candidates are not used. If that LAN path is missing
or unreachable, live playback fails instead of choosing a public candidate.

This option is off by default to preserve existing routing behavior. Changing it
reloads the integration and closes active camera sessions. Cloud authorization,
signaling and connection setup remain necessary, and this option does not prevent
independent uploads by the camera. It governs live video, not cloud snapshots.
