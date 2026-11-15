import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { beforeEach, test } from "node:test";
import { fileURLToPath } from "node:url";
import { importFrontend } from "./support.mjs";

/** Each language answers with its real file unless a test fails it or holds it back. */
const requests = [];
const behavior = new Map();
globalThis.fetch = async (input) => {
  const url = new URL(String(input));
  requests.push(url.pathname.match(/([^/]+)\.json$/)[1]);
  const mode = behavior.get(requests.at(-1));
  if (mode === "fail") return new Response("", { status: 503 });
  if (mode instanceof Promise) await mode;
  return new Response(await readFile(fileURLToPath(url), "utf8"));
};
let copies = 0;
const freshTranslations = () => importFrontend("i18n.js", `copy=${++copies}`);

beforeEach(() => {
  requests.length = 0;
  behavior.clear();
});

test("a slow response does not replace a newer language choice", async () => {
  const i18n = await freshTranslations();
  await i18n.loadTranslations("en");
  let answerRussian;
  behavior.set("ru", new Promise((resolve) => (answerRussian = resolve)));
  const russian = i18n.loadTranslations("ru");
  await i18n.loadTranslations("en");
  answerRussian();
  await russian;
  assert.equal(i18n.t("door.open"), "Open");
  assert.equal(i18n.currentLocale(), "en");
  assert.equal(i18n.tp("summary.open", 2), "2 doors are open");
});

test("strings that failed to load are fetched again by the next load", async () => {
  const i18n = await freshTranslations();
  behavior.set("en", "fail");
  await i18n.loadTranslations("en");
  assert.equal(i18n.t("door.open"), "door.open");
  assert.ok(!i18n.translationsLoaded());
  behavior.delete("en");
  await i18n.loadTranslations("en");
  assert.equal(i18n.t("door.open"), "Open");
  assert.ok(i18n.translationsLoaded());
  assert.deepEqual(requests, ["en", "en"]);
});

test("a language that failed to load shows English until it loads", async () => {
  const i18n = await freshTranslations();
  behavior.set("de", "fail");
  await i18n.loadTranslations("de");
  assert.equal(i18n.t("door.open"), "Open");
  behavior.delete("de");
  await i18n.loadTranslations("de");
  assert.equal(i18n.t("door.open"), "Öffnen");
});

test("a loaded language is not fetched again", async () => {
  const i18n = await freshTranslations();
  await i18n.loadTranslations("fr");
  await i18n.loadTranslations("fr");
  assert.deepEqual(requests.sort(), ["en", "fr"]);
});
