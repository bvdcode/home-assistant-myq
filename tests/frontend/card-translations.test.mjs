import assert from "node:assert/strict";
import { test } from "node:test";
import { answering, cover, flush, importFrontend, installPage, makeHass, until } from "./support.mjs";

installPage();
let englishDown = true;
let englishRequests = 0;
const fileFetch = globalThis.fetch;
globalThis.fetch = async (input) => {
  if (String(input).endsWith("/i18n/en.json")) {
    englishRequests += 1;
    if (englishDown) return new Response("", { status: 503 });
  }
  return fileFetch(input);
};
await importFrontend("myq-card.js");

const door = { device_id: "dev-a", name: "Door A", model: "Opener", entities: { cover: "cover.door_a" } };
const makeDoorHass = () =>
  makeHass({
    states: { "cover.door_a": cover("cover.door_a", "closed") },
    subscribe: answering(() => ({ doors: [door], cameras: [], appearance: {}, settings: {} })),
  });

test("a card shown again fetches strings that failed to load", async () => {
  const card = document.createElement("myq-door-card");
  card.setConfig({ type: "custom:myq-door-card", entity: "cover.door_a" });
  document.body.append(card);
  card.hass = makeDoorHass();
  const label = () => card.shadowRoot.querySelector("button.action.open")?.getAttribute("aria-label");
  await until(() => label()?.endsWith("Door A"), "the card");
  assert.equal(label(), "door.open: Door A", "while en.json fails, keys show");

  englishDown = false;
  card.remove();
  document.body.append(card);
  card.hass = makeDoorHass();
  await until(() => label() === "Open: Door A", "translated text");

  const requests = englishRequests;
  for (let i = 0; i < 5; i += 1) card.hass = makeDoorHass();
  await flush();
  assert.equal(englishRequests, requests, "routine updates fetch nothing more");
  card.remove();
});
