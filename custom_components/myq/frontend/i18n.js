/** Panel translations loaded from ./i18n/<language>.json with English as the fallback. */

const AVAILABLE = ["cs", "da", "de", "en", "es", "fr", "it", "nl", "pl", "pt-BR", "ru", "sv", "zh-Hans"];
const cache = new Map();
let strings = {};
let fallback = {};
let active = "";
let locale = "en";
let plurals = new Intl.PluralRules("en");

/** Map a Home Assistant language code to the closest bundled translation. */
export function resolveLanguage(code) {
  if (!code) return "en";
  if (AVAILABLE.includes(code)) return code;
  const base = code.split("-")[0].toLowerCase();
  if (base === "pt") return "pt-BR";
  if (base === "zh") return "zh-Hans";
  return AVAILABLE.find((language) => language.toLowerCase() === base) ?? "en";
}

async function fetchStrings(language) {
  if (!cache.has(language)) {
    const url = new URL(`./i18n/${language}.json`, import.meta.url);
    cache.set(
      language,
      fetch(url)
        .then((response) => (response.ok ? response.json() : {}))
        .catch(() => ({})),
    );
  }
  return cache.get(language);
}

/** Load translations for a language; resolves once strings are ready. Returns true if they changed. */
export async function loadTranslations(code) {
  const language = resolveLanguage(code);
  locale = code || "en";
  if (language === active) return false;
  const [english, selected] = await Promise.all([fetchStrings("en"), fetchStrings(language)]);
  fallback = english;
  strings = selected;
  active = language;
  try {
    plurals = new Intl.PluralRules(locale);
  } catch {
    plurals = new Intl.PluralRules("en");
  }
  return true;
}

export function currentLocale() {
  return locale;
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
