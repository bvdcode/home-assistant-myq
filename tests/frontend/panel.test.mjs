import assert from "node:assert/strict";
import { before, test } from "node:test";
import { answering, cover, flush, importFrontend, installPage, makeHass, until } from "./support.mjs";

installPage();
await importFrontend("myq-panel.js");

const doors = [
  { device_id: "dev-a", name: "Door A", model: "Opener", entities: { cover: "cover.door_a" } },
  { device_id: "dev-b", name: "Door B", model: "Opener", entities: { cover: "cover.door_b" } },
];
const tenMinutesAgo = new Date(Date.now() - 10 * 60000).toISOString();
const hass = (a, b, aChanged = tenMinutesAgo) =>
  makeHass({
    states: { "cover.door_a": cover("cover.door_a", a, aChanged), "cover.door_b": cover("cover.door_b", b, tenMinutesAgo) },
    subscribe: answering(() => ({ doors, cameras: [], appearance: {}, settings: {}, accounts: [] })),
  });

let panel;
const title = () => panel.shadowRoot.querySelector(".summary-title")?.textContent ?? "";
const subtitle = () => panel.shadowRoot.querySelector(".summary-sub")?.textContent ?? "";

before(async () => {
  panel = document.createElement("myq-panel");
  document.body.append(panel);
  panel.hass = hass("closed", "closed");
  panel.panel = { config: {} };
  panel.narrow = false;
  await until(() => title() !== "", "the summary");
});

const cases = [
  ["closed", "closed", "All doors are closed"],
  ["open", "closed", "1 door is open"],
  ["closed", "unavailable", "1 door is unavailable"],
  ["closed", "unknown", "1 door has an unknown position"],
  ["unknown", "unknown", "2 doors have an unknown position"],
  ["open", "unknown", "1 door is open", "1 door has an unknown position"],
  ["unavailable", "unknown", "1 door is unavailable", "1 door has an unknown position"],
];
for (const [a, b, expectedTitle, expectedSubtitle] of cases) {
  test(`the summary for ${a} and ${b} doors reads "${expectedTitle}"`, async () => {
    panel.hass = hass(a, b);
    await flush();
    assert.equal(title(), expectedTitle);
    if (expectedSubtitle) assert.equal(subtitle(), expectedSubtitle);
  });
}

test("the summary keeps a door left open through a failed poll", async () => {
  panel.hass = hass("closed", "closed");
  await flush();
  panel.hass = hass("open", "closed", new Date(Date.now() - 2 * 3600000).toISOString());
  await flush();
  const before = subtitle();
  assert.match(before, /^Door A has been open for /);
  const now = new Date().toISOString();
  panel.hass = hass("unavailable", "closed", now);
  await flush();
  panel.hass = hass("open", "closed", now);
  await flush();
  assert.equal(subtitle(), before);
});
