import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { answering, cover, fakeConnection, flush, importFrontend, installClock, installPage, makeHass, until } from "./support.mjs";

installPage();
const clock = installClock();
await importFrontend("myq-card.js");

const DOOR_A = { device_id: "dev-a", name: "Door A", model: "Opener", entities: { cover: "cover.door_a" } };
const DOOR_B = { device_id: "dev-b", name: "Door B", model: "Opener", entities: { cover: "cover.door_b" } };
const confirming = () => ({ doors: [DOOR_A, DOOR_B], cameras: [], appearance: {}, settings: { confirm: true } });
const closed = () => ({ "cover.door_a": cover("cover.door_a", "closed"), "cover.door_b": cover("cover.door_b", "closed") });

let card = null;
afterEach(async () => {
  card?.remove();
  card = null;
  // Past the five seconds after which the cards' shared subscription is released.
  await clock.advance(6000);
});

function mount(hass, entity = "cover.door_a") {
  card = document.createElement("myq-door-card");
  card.setConfig({ type: "custom:myq-door-card", entity });
  document.body.append(card);
  card.hass = hass;
}
const root = () => card.shadowRoot;
const openButton = () => root().querySelector("button.action.open");
const openLabel = () => openButton()?.getAttribute("aria-label");
const shown = (element) => {
  for (let node = element; node && node !== root(); node = node.parentNode) if (node.hidden) return false;
  return true;
};
const activityRows = () => [...root().querySelectorAll(".activity-row")].filter(shown).length;

test("a card switched to another door leaves the first door's state behind", async () => {
  const calls = [];
  const now = Date.now() / 1000;
  const logbook = {
    "cover.door_a": [
      { when: now - 7200, state: "open", entity_id: "cover.door_a" },
      { when: now - 3600, state: "closed", entity_id: "cover.door_a" },
    ],
  };
  mount(
    makeHass({
      states: closed(),
      subscribe: answering(confirming),
      callWS: async (message) => logbook[message.entity_ids[0]] ?? [],
      components: ["logbook"],
      calls,
    }),
  );
  await until(() => openLabel() === "Open: Door A", "door A");
  root().querySelector("button.details-toggle").click();
  await clock.advance(0);
  await until(() => activityRows() === 2, "door A's activity");
  openButton().click();
  assert.deepEqual(calls, [], "the first tap only asks for confirmation");

  card.setConfig({ type: "custom:myq-door-card", entity: "cover.door_b" });
  await flush();
  assert.equal(openLabel(), "Open: Door B", "door B is not waiting for door A's confirmation");
  assert.equal(activityRows(), 0, "none of door A's activity is shown");
  openButton().click();
  await flush();
  assert.deepEqual(calls, [], "one tap on door B only asks for confirmation");
});

test("updates for the same door keep its door card", async () => {
  let push = null;
  mount(
    makeHass({
      states: closed(),
      subscribe: async (callback) => {
        push = callback;
        callback(confirming());
        return () => {};
      },
    }),
  );
  await until(() => openLabel() === "Open: Door A", "door A");
  const doorCard = root().querySelector(".door-card");
  push(confirming());
  await flush();
  assert.equal(root().querySelector(".door-card"), doorCard);
});

test("a card shown again asks for confirmation until its settings arrive", async () => {
  const calls = [];
  let subscriptions = 0;
  let answer = null;
  mount(
    makeHass({
      states: closed(),
      subscribe: async (callback) => {
        subscriptions += 1;
        if (subscriptions === 1) callback(confirming());
        else answer = () => callback(confirming());
        return () => {};
      },
      calls,
    }),
  );
  await until(() => openLabel() === "Open: Door A", "door A");
  card.remove();
  await clock.advance(6000);
  document.body.append(card);
  await flush();
  assert.ok(answer, "the card subscribes again");

  openButton().click();
  await flush();
  assert.deepEqual(calls, [], "before the settings arrive, one tap sends nothing");
  answer();
  await flush();
  openButton().click();
  await flush();
  assert.deepEqual(calls, ["cover.open_cover cover.door_a"], "the confirming tap opens the door");
});

test("a card subscribes again after Home Assistant restarts", async () => {
  let loaded = true;
  let name = "Door A";
  const connection = fakeConnection(async (callback) => {
    if (!loaded) throw { code: "unknown_command", message: "Unknown command." };
    callback({ doors: [{ ...DOOR_A, name }], cameras: [], appearance: {}, settings: {} });
    return () => {};
  });
  mount(makeHass({ states: closed(), connection }));
  await until(() => openLabel() === "Open: Door A", "door A");

  // Home Assistant restarts: the websocket is back before MyQ has loaded, and meanwhile the door was renamed.
  loaded = false;
  name = "Front door";
  connection.reconnect();
  await flush();
  loaded = true;
  await clock.advance(10000);
  assert.equal(openLabel(), "Open: Front door");
});
