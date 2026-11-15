import assert from "node:assert/strict";
import { test } from "node:test";
import { answering, cover, decoded, flush, importFrontend, installClock, installPage, makeHass, setOnScreen, until } from "./support.mjs";

installPage();
const clock = installClock();
await importFrontend("myq-card.js");

const door = { device_id: "dev-a", name: "Door A", model: "Opener", entities: { cover: "cover.door_a", camera: "camera.door_a" } };
const hass = (coverState) =>
  makeHass({
    states: {
      "cover.door_a": cover("cover.door_a", coverState),
      "camera.door_a": {
        entity_id: "camera.door_a",
        state: "idle",
        attributes: { entity_picture: "/api/camera_proxy/camera.door_a?token=t", supported_features: 2 },
      },
    },
    subscribe: answering(() => ({ doors: [door], cameras: [], appearance: {}, settings: {} })),
  });
const snapshots = () => decoded.filter((source) => source.startsWith("/api/camera_proxy/")).length;

test("only a card on screen fetches a snapshot after its door moves", async () => {
  const card = document.createElement("myq-door-card");
  card.setConfig({ type: "custom:myq-door-card", entity: "cover.door_a" });
  document.body.append(card);
  card.hass = hass("closed");
  await until(() => card.shadowRoot.querySelector(".door-card"), "the door card");
  const doorCard = card.shadowRoot.querySelector(".door-card");
  const peek = card.shadowRoot.querySelector(".peek");
  const move = async (through, to) => {
    card.hass = hass(through);
    await flush();
    card.hass = hass(to);
    // The card waits for the camera to catch up before taking the snapshot.
    await clock.advance(2000);
  };

  setOnScreen(doorCard, false);
  let before = snapshots();
  await move("opening", "open");
  assert.equal(snapshots(), before, "off screen: no snapshot");
  assert.ok(peek.hidden, "off screen: no preview");

  setOnScreen(doorCard, true);
  before = snapshots();
  await move("closing", "closed");
  assert.equal(snapshots(), before + 1, "on screen: one snapshot");
  assert.ok(!peek.hidden, "on screen: the preview shows");
  card.remove();
});
