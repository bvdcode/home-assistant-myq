# Use a MyQ garage camera in Frigate

This setup uses Home Assistant Container with host networking and Frigate on a
Docker bridge on the same host. Home Assistant's built-in go2rtc makes the
camera stream available over RTSP. A user confirmed this layout with an
opener-mounted camera in [issue #33](https://github.com/bvdcode/home-assistant-myq/issues/33#issuecomment-7143021315).

## Prepare the camera in Home Assistant

1. Under **Settings → Devices & services → MyQ → Configure**, enable
   **Require LAN-only camera video**. Open the TC camera in Home Assistant and
   confirm live video plays.
2. In the camera entity's settings, enable **Preload camera stream**. This
   keeps the video session active for Frigate. Use a powered garage camera
   for continuous viewing. Leave preloading off on a battery Video Keypad.
3. On the opener's device page, find its serial number under **Device info**.
   The RTSP stream name for an attached camera is `myq_<opener-serial>_camera`.

## Connect the Frigate container

Home Assistant's go2rtc listens on `127.0.0.1:18554`. To reach it from Frigate,
forward TCP through the host's Docker bridge. Find Frigate's IPv4 address and
gateway on that bridge with `docker inspect <frigate-container>` under
`NetworkSettings.Networks`.

For example, if the gateway is `172.17.0.1` and Frigate is `172.17.0.2`, run
this on the Docker host with `socat` installed. Substitute both addresses for
your network. The listener accepts connections from the Frigate address only.

```sh
socat TCP4-LISTEN:18554,bind=172.17.0.1,range=172.17.0.2/32,reuseaddr,fork TCP4:127.0.0.1:18554
```

In Frigate's configuration, add the camera under `cameras`. Use the same
gateway and replace `<opener-serial>` with the serial from Home Assistant.

```yaml
cameras:
  garage:
    ffmpeg:
      inputs:
        - path: "rtsp://172.17.0.1:18554/myq_<opener-serial>_camera"
          roles:
            - detect
```

Apply the configuration and open **garage** in Frigate. Once video plays,
configure the forwarder to start after reboot and keep the Frigate container's
IP address fixed so the access rule continues to match.
