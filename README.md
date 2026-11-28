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
- on/off controls for standalone MyQ light switches and remote lights;
- a door-open binary sensor for Alarmo and other sensor-based automations;
- vacation mode, work-light, fault, cycle-count, and activation diagnostics
  when provided by MyQ;
- snapshots from attached and standalone cameras and experimental live video for TC cameras;
- cloud polling every 2 minutes, temporarily more frequently after a command.

## Requirements

- Home Assistant 2026.7.4 or newer;
- a MyQ residential account with at least one connected garage-door opener,
  camera, or light control.

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

## Alarmo

In Alarmo's **Sensors** tab, add the **Door open** binary sensor for each garage
door. It stays on while the door is open or moving. See [door states and polling](docs/garage-doors.md)
for how quickly changes appear.

## Light controls

Standalone MyQ light controls get an on/off light entity using their MyQ name.
Accounts containing only light controls can also be added. Brightness and direct
control of an opener's built-in work light are not supported; the existing
work-light binary sensor reports its state only.

After a light command, status polling starts after 1 second and slows to a
5-second interval until MyQ reports the requested state, for up to 60 seconds.
Light entities always show the state reported by MyQ. Real-device validation
of light commands and state updates is pending.

## Cameras

Attached cameras appear on their opener's device page. Standalone cameras,
including the Video Keypad, get their own device. TC cameras support experimental
live video. See the [camera guide](docs/cameras.md) for snapshots, keypad battery
use and LAN-only video, or [connect a garage camera to Frigate](docs/frigate.md).

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
