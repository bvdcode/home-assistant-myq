import assert from "node:assert/strict";
import { test } from "node:test";
import { decoded, importFrontend, installClock, installPage } from "./support.mjs";

installPage();
customElements.define("ha-camera-stream", class extends HTMLElement {});
const clock = installClock();
const { CameraView } = await importFrontend("camera-view.js");

let token = 0;
const hass = (state) => ({
  states: {
    "camera.garage": {
      entity_id: "camera.garage",
      state,
      attributes:
        state === "unavailable"
          ? {}
          : { supported_features: 2, entity_picture: `/api/camera_proxy/camera.garage?token=t${++token}` },
    },
  },
});

test("snapshots resume after live video, an outage, and recovery", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const camera = new CameraView(host);
  host.append(camera.el);
  camera.setEntity("camera.garage");
  camera.update(hass("idle"));
  camera.activate();
  await clock.advance(0);
  assert.equal(decoded.length, 1, "the first snapshot loads when the camera is shown");

  await camera.toggleLive();
  assert.ok(camera.live);
  await clock.advance(5000);
  camera.update(hass("unavailable"));
  assert.ok(!camera.live, "live video stops when the camera goes away");
  await clock.advance(5000);
  camera.update(hass("idle"));
  const before = decoded.length;
  await clock.advance(61000);
  assert.equal(decoded.length - before, 2, "two snapshots in the next 61 seconds");
  camera.destroy();
});
