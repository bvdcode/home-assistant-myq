import assert from "node:assert/strict";
import { test } from "node:test";
import { cover, fakeConnection, flush, importFrontend, installClock, installPage, makeHass, until } from "./support.mjs";

installPage();
const clock = installClock();
await importFrontend("myq-panel.js");

test("the panel subscribes again after Home Assistant restarts", async () => {
  let loaded = true;
  let name = "Door A";
  const connection = fakeConnection(async (callback) => {
    if (!loaded) throw { code: "unknown_command", message: "Unknown command." };
    callback({
      doors: [{ device_id: "dev-a", name, model: "Opener", entities: { cover: "cover.door_a" } }],
      cameras: [],
      appearance: {},
      settings: {},
      accounts: [],
    });
    return () => {};
  });
  const panel = document.createElement("myq-panel");
  document.body.append(panel);
  panel.hass = makeHass({ states: { "cover.door_a": cover("cover.door_a", "closed") }, connection });
  panel.panel = { config: {} };
  panel.narrow = false;
  const doorName = () => panel.shadowRoot.querySelector(".door-card .name")?.textContent;
  await until(() => doorName() === "Door A", "door A");

  // Home Assistant restarts: the websocket is back before MyQ has loaded, and meanwhile the door was renamed.
  loaded = false;
  name = "Front door";
  connection.reconnect();
  await flush();
  loaded = true;
  await clock.advance(10000);
  assert.equal(doorName(), "Front door");
  panel.remove();
});
