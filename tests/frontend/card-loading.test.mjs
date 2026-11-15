import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";

// Home Assistant loads the card module on every page, so note each module the card brings in.
const loaded = new Set();
registerHooks({
  resolve(specifier, context, nextResolve) {
    const result = nextResolve(specifier, context);
    loaded.add(new URL(result.url).pathname.split("/").pop());
    return result;
  },
});

const { answering, cover, importFrontend, installPage, makeHass, until } = await import("./support.mjs");
installPage();
await importFrontend("myq-card.js");

const DRAWING = ["door-card.js", "door-scene.js", "camera-view.js", "dialogs.js", "styles.js"];
const door = { device_id: "dev-a", name: "Door A", model: "Opener", entities: { cover: "cover.door_a" } };

test("a page without a card loads none of the card's drawing, camera, or dialog code", () => {
  assert.ok(loaded.has("myq-card.js"));
  assert.deepEqual(DRAWING.filter((name) => loaded.has(name)), []);
});

test("the first card shown loads the rest and draws its door", async () => {
  const card = document.createElement("myq-door-card");
  card.setConfig({ type: "custom:myq-door-card", entity: "cover.door_a" });
  document.body.append(card);
  card.hass = makeHass({
    states: { "cover.door_a": cover("cover.door_a", "closed") },
    subscribe: answering(() => ({ doors: [door], cameras: [], appearance: {}, settings: {} })),
  });
  await until(() => card.shadowRoot.querySelector("button.action.open"), "the door");
  assert.deepEqual(DRAWING.filter((name) => !loaded.has(name)), []);
  assert.ok(card.shadowRoot.querySelector("style").textContent.includes(".door-card"), "the card is styled");
  card.remove();
});
