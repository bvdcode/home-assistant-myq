import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { answering, cover, decoded, flush, importFrontend, installClock, installPage, makeHass, setOnScreen, until } from "./support.mjs";

const window = installPage();
const clock = installClock();
await importFrontend("myq-card.js");

const door = { device_id: "dev-a", name: "Door A", model: "Opener", entities: { cover: "cover.door_a", camera: "camera.door_a" } };
const doorHass = (coverState, logbook = [], lastChanged = undefined) =>
  makeHass({
    states: {
      "cover.door_a": cover("cover.door_a", coverState, lastChanged),
      "camera.door_a": {
        entity_id: "camera.door_a",
        state: "idle",
        attributes: { entity_picture: "/api/camera_proxy/camera.door_a?token=t", supported_features: 2 },
      },
    },
    subscribe: answering(() => ({ doors: [door], cameras: [], appearance: {}, settings: {} })),
    callWS: async () => logbook.map((entry) => ({ ...entry, entity_id: "cover.door_a" })),
    components: ["logbook"],
  });
const snapshots = () => decoded.filter((source) => source.startsWith("/api/camera_proxy/")).length;

let card = null;
afterEach(async () => {
  card?.remove();
  card = null;
  await clock.advance(6000);
});

async function mount(hass) {
  card = document.createElement("myq-door-card");
  card.setConfig({ type: "custom:myq-door-card", entity: "cover.door_a" });
  document.body.append(card);
  card.hass = hass;
  await until(() => card.shadowRoot.querySelector(".door-card"), "the door card");
}
const peek = () => card.shadowRoot.querySelector(".peek");
const setState = async (state) => {
  card.hass = doorHass(state);
  await flush();
};
const activityRows = async () => {
  card.shadowRoot.querySelector("button.details-toggle").click();
  await clock.advance(0);
  await until(() => !card.shadowRoot.querySelector(".activity").hidden, "the activity");
  return card.shadowRoot.querySelectorAll(".activity-row").length;
};

test("only a card on screen fetches a snapshot after its door moves", async () => {
  await mount(doorHass("closed"));
  const doorCard = card.shadowRoot.querySelector(".door-card");
  setOnScreen(doorCard, false);
  let before = snapshots();
  await setState("opening");
  await setState("open");
  await clock.advance(2000);
  assert.equal(snapshots(), before, "off screen: no snapshot");
  assert.ok(peek().hidden, "off screen: no preview");

  setOnScreen(doorCard, true);
  before = snapshots();
  await setState("closing");
  await setState("closed");
  await clock.advance(2000);
  assert.equal(snapshots(), before + 1, "on screen: one snapshot");
  assert.ok(!peek().hidden, "on screen: the preview shows");
});

test("a door coming back online is not listed as a new change", async () => {
  const now = Date.now() / 1000;
  await mount(
    doorHass("closed", [
      { when: now - 5000, state: "closed" },
      { when: now - 4000, state: "unavailable" },
      { when: now - 3000, state: "closed" },
      { when: now - 2000, state: "unavailable" },
      { when: now - 1000, state: "closed" },
    ]),
  );
  assert.equal(await activityRows(), 1);
});

test("a door that moves and stops in the same state is listed for each stop", async () => {
  const now = Date.now() / 1000;
  await mount(
    doorHass("closed", [
      { when: now - 3000, state: "closed" },
      { when: now - 2000, state: "opening" },
      { when: now - 1000, state: "closed" },
    ]),
  );
  assert.equal(await activityRows(), 2);
});

test("a door that moves again before its snapshot is taken shows no snapshot", async () => {
  await mount(doorHass("closed"));
  const before = snapshots();
  await setState("opening");
  await setState("open");
  await clock.advance(500);
  await setState("closing");
  await clock.advance(2000);
  assert.equal(snapshots(), before, "no snapshot is requested");
  assert.ok(peek().hidden, "no preview shows over the moving door");
});

test("a snapshot that arrives after the door moves again is not shown", async () => {
  await mount(doorHass("closed"));
  const decode = window.HTMLImageElement.prototype.decode;
  let finish = null;
  window.HTMLImageElement.prototype.decode = function decodeSlowly() {
    decoded.push(this.getAttribute("src") ?? "");
    return new Promise((resolve) => (finish = resolve));
  };
  try {
    await setState("opening");
    await setState("open");
    await clock.advance(2000);
    assert.ok(finish, "the snapshot is loading");
    await setState("closing");
    finish();
    await flush();
    assert.ok(peek().hidden, "the late snapshot stays hidden");
  } finally {
    window.HTMLImageElement.prototype.decode = decode;
  }
});

test("an open door keeps its open time through a failed poll", async () => {
  await mount(doorHass("open", [], new Date(clock.now - 2 * 3600000).toISOString()));
  const doorCard = card.shadowRoot.querySelector(".door-card");
  const subtitle = () => card.shadowRoot.querySelector(".subtitle").textContent;
  assert.ok(doorCard.classList.contains("left-open"), "open for two hours: highlighted");
  const before = subtitle();

  // A failed poll makes the door unavailable; the next one finds it open with a new last_changed.
  await setState("unavailable");
  await setState("open");
  assert.ok(doorCard.classList.contains("left-open"), "still highlighted");
  assert.equal(subtitle(), before, "still counting from when it opened");

  await setState("closing");
  await setState("closed");
  await setState("open");
  assert.ok(!doorCard.classList.contains("left-open"), "opened again: counting starts over");
});
