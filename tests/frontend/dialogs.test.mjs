import assert from "node:assert/strict";
import { test } from "node:test";
import { importFrontend, installPage } from "./support.mjs";

installPage();
const { CustomizeDialog, SettingsDialog } = await importFrontend("dialogs.js");
const { loadTranslations } = await importFrontend("i18n.js");
await loadTranslations("en");

const door = { device_id: "dev-a", name: "Main garage", entities: { cover: "cover.main" } };
/** The parts of the panel that the dialogs use. */
const host = Object.assign(document.createElement("div"), {
  hass: { user: { is_admin: true }, callWS: async () => ({}) },
  settings: { confirm: false, open_warning: 30 },
  orderedDoors: () => [door],
  appearanceFor: () => undefined,
});
host.attachShadow({ mode: "open" });
document.body.append(host);
const dialogs = () => [
  ["Customize", new CustomizeDialog(host, door, [door], undefined).dialog],
  ["Settings", new SettingsDialog(host).dialog],
];

test("each dialog is named by its title", () => {
  for (const [name, dialog] of dialogs()) {
    const title = dialog.querySelector(`[id="${dialog.getAttribute("aria-labelledby")}"]`);
    assert.equal(title?.tagName, "H2", name);
    assert.ok(title.textContent.trim(), name);
  }
});

test("dialog titles have distinct ids", () => {
  const ids = dialogs().map(([, dialog]) => dialog.getAttribute("aria-labelledby"));
  assert.equal(new Set(ids).size, ids.length);
});

test("a press that starts inside the dialog and ends outside keeps it open", () => {
  const sheet = new CustomizeDialog(host, door, [door], undefined);
  let closed = false;
  const destroy = sheet.onClose;
  sheet.onClose = () => {
    closed = true;
    destroy();
  };
  const dialog = sheet.dialog;
  const inside = dialog.querySelector(".tile");
  // The click after a drag targets the nearest common ancestor: the dialog itself.
  inside.dispatchEvent(new Event("pointerdown", { bubbles: true }));
  dialog.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.ok(!closed, "a drag out of the dialog keeps it open");

  dialog.dispatchEvent(new Event("pointerdown", { bubbles: true }));
  dialog.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  assert.ok(closed, "a click on the backdrop closes it");
});

test("every option group is named", () => {
  for (const [name, dialog] of dialogs()) {
    const groups = [...dialog.querySelectorAll('[role="group"]')];
    assert.ok(groups.length > 0, name);
    for (const group of groups) assert.ok(group.getAttribute("aria-label"), `${name}: ${group.textContent}`);
  }
});
