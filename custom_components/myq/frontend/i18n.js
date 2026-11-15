/** Panel translations loaded from ./i18n/<language>.json with English as the fallback. */

const AVAILABLE = ["cs", "da", "de", "en", "es", "fr", "it", "nl", "pl", "pt-BR", "ru", "sv", "zh-Hans"];
const cache = new Map();
let strings = {};
let fallback = {};
let active = "";
let locale = "en";
let plurals = new Intl.PluralRules("en");
/** Counts loadTranslations calls, so a slow response cannot replace a newer choice. */
let latest = 0;

/** Map a Home Assistant language code to the closest bundled translation. */
export function resolveLanguage(code) {
  if (!code) return "en";
  if (AVAILABLE.includes(code)) return code;
  const base = code.split("-")[0].toLowerCase();
  if (base === "pt") return "pt-BR";
  if (base === "zh") return "zh-Hans";
  return AVAILABLE.find((language) => language.toLowerCase() === base) ?? "en";
}

/** Resolves to a language's strings, or null if they could not be loaded. */
async function fetchStrings(language) {
  if (!cache.has(language)) {
    const url = new URL(`./i18n/${language}.json`, import.meta.url);
    const request = fetch(url)
      .then((response) => (response.ok ? response.json() : null))
      .catch(() => null);
    cache.set(language, request);
    // Forget a failed load, so the next call asks again instead of keeping nothing for good.
    request.then((table) => {
      if (!table) cache.delete(language);
    });
  }
  return cache.get(language);
}

/** Load translations for a language; resolves once strings are ready. Returns true if they changed. */
export async function loadTranslations(code) {
  const call = ++latest;
  const language = resolveLanguage(code);
  let changed = false;
  if (language !== active) {
    const [english, selected] = await Promise.all([fetchStrings("en"), fetchStrings(language)]);
    // A later call chose a language while these loaded, so its choice stands.
    if (call !== latest) return false;
    fallback = english ?? fallback;
    strings = selected ?? {};
    // A language counts as loaded only once its strings and the English fallback arrived, so the
    // next call fetches whatever failed again.
    active = english && selected ? language : "";
    changed = true;
  }
  // The locale and plural rules change together with the strings they format.
  locale = code || "en";
  try {
    plurals = new Intl.PluralRules(locale);
  } catch {
    plurals = new Intl.PluralRules("en");
  }
  return changed;
}

export function currentLocale() {
  return locale;
}

/** Whether the last load brought in every string it asked for. */
export function translationsLoaded() {
  return active !== "";
}

function lookup(table, key) {
  let node = table;
  for (const part of key.split(".")) {
    if (node == null || typeof node !== "object") return undefined;
    node = node[part];
  }
  return node;
}

function format(template, params) {
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

/** Translate a key such as "door.open", replacing {placeholders} with params. */
export function t(key, params = {}) {
  const value = lookup(strings, key) ?? lookup(fallback, key);
  return typeof value === "string" ? format(value, params) : key;
}

/** Translate a pluralized key using the language's plural rules; {count} is always available. */
export function tp(key, count, params = {}) {
  const forms = lookup(strings, key) ?? lookup(fallback, key);
  if (!forms || typeof forms !== "object") return key;
  const category = plurals.select(count);
  const template = forms[category] ?? forms.other ?? Object.values(forms)[0];
  return format(String(template), { count: count.toLocaleString(locale), ...params });
}
